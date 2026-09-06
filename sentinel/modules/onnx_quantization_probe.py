import hashlib
import os
import tempfile

import numpy as np
import onnxruntime as ort
from onnxruntime.quantization import CalibrationDataReader, QuantFormat, QuantType, quantize_static
from scipy.spatial.distance import jensenshannon
from scipy.stats import weightedtau
from torch.utils.data import DataLoader


class CalibrationBatchReader(CalibrationDataReader):
    """Feeds the calibration subset to the ONNX Static Quantizer."""

    def __init__(self, dataloader: DataLoader, input_name: str):
        self.dataloader = dataloader
        self.input_name = input_name
        self.iterator = iter(self.dataloader)

    def get_next(self):
        try:
            images, _ = next(self.iterator)
            return {self.input_name: images.numpy()}
        except StopIteration:
            return None


class ONNXQuantizationProbe:
    # Methodology version: Bumping required if JSD, tau, or margin logic changes.
    METHODOLOGY_VERSION = "v1.2.0-strict-cache-disjoint"

    def __init__(self):
        pass

    def _extract_sample_ids(self, dataloader) -> set[str]:
        """
        Extracts canonical sample identifiers from the Sentinel dataset manifest.
        Fails loudly on type mismatches or missing identifiers.
        """
        if not isinstance(dataloader, DataLoader):
            raise TypeError(
                f"CRITICAL: Expected torch.utils.data.DataLoader, got {type(dataloader).__name__}. "
                "Cannot reliably extract dataset manifest from raw iterables."
            )

        dataset = getattr(dataloader, "dataset", None)
        if dataset is None:
            raise ValueError("CRITICAL: DataLoader does not expose a 'dataset' attribute.")

        sample_ids = getattr(dataset, "manifest_sample_ids", None)
        if sample_ids is None or len(sample_ids) == 0:
            raise ValueError(
                "CRITICAL: Dataset does not expose 'manifest_sample_ids'. "
                "Cannot cryptographically verify disjointness between "
                "calibration and evaluation sets."
            )
        return set(sample_ids)

    def _verify_disjoint(self, calib_dataloader, eval_dataloader):
        """
        Actively prevents evaluation contamination by comparing exact sample identifiers.
        """
        calib_ids = self._extract_sample_ids(calib_dataloader)
        eval_ids = self._extract_sample_ids(eval_dataloader)

        overlap = calib_ids.intersection(eval_ids)
        if overlap:
            raise ValueError(
                f"CRITICAL: {len(overlap)} sample_id(s) present in both "
                "calibration and evaluation sets. "
                "Evaluation data must never be used to fit INT8 ranges."
            )

    @classmethod
    def generate_cache_key(
        cls,
        reference_paths: list[str],
        calib_dataloader,
        eval_dataloader,
        quant_format: QuantFormat,
        weight_type: QuantType,
        activation_type: QuantType,
    ) -> str:
        """
        Computes a cryptographic cache key binding the thresholds to the exact state.
        """
        calib_hash = getattr(calib_dataloader, "manifest_hash", None)
        eval_hash = getattr(eval_dataloader, "manifest_hash", None)

        if calib_hash is None or eval_hash is None:
            raise ValueError(
                "CRITICAL: Dataloaders must expose 'manifest_hash' for cache-key correctness. "
                "Silently defaulting to a placeholder invites cache poisoning."
            )

        model_string = "".join(sorted(reference_paths))
        quant_string = f"{quant_format.name}_{weight_type.name}_{activation_type.name}"

        raw_key = (
            f"{cls.METHODOLOGY_VERSION}_{model_string}_{calib_hash}_{eval_hash}_{quant_string}"
        )
        return hashlib.sha256(raw_key.encode()).hexdigest()

    def compute_divergence_metrics(self, fp32_path: str, int8_path: str, eval_dataloader) -> dict:
        """Runs the FP32 vs INT8 comparison and extracts structural ranking collapses."""
        session_fp32 = ort.InferenceSession(fp32_path, providers=["CPUExecutionProvider"])
        session_int8 = ort.InferenceSession(int8_path, providers=["CPUExecutionProvider"])
        input_name = session_fp32.get_inputs()[0].name

        jsd_scores, weighted_tau_scores = [], []
        margin_weighted_flip_penalty = 0.0
        degenerate_count, total_samples = 0, 0

        for images, _ in eval_dataloader:
            img_batch = images.numpy()
            total_samples += img_batch.shape[0]

            logits_fp32 = session_fp32.run(None, {input_name: img_batch})[0]
            logits_int8 = session_int8.run(None, {input_name: img_batch})[0]

            probs_fp32 = self._softmax(logits_fp32)
            probs_int8 = self._softmax(logits_int8)

            for i in range(img_batch.shape[0]):
                p32, p8 = probs_fp32[i], probs_int8[i]

                jsd = jensenshannon(p32, p8)
                if np.isnan(jsd) or np.isinf(jsd):
                    degenerate_count += 1
                else:
                    jsd_scores.append(float(jsd))

                rank32 = np.argsort(p32)[::-1]
                rank8 = np.argsort(p8)[::-1]
                if rank32[0] != rank8[0]:
                    margin = p32[rank32[0]] - p32[rank32[1]]
                    margin_weighted_flip_penalty += margin

                tau, _ = weightedtau(p32, p8)
                weighted_tau_scores.append(tau if not np.isnan(tau) else 0.0)

        return {
            "mean_jsd": float(np.mean(jsd_scores)) if jsd_scores else 0.0,
            "margin_weighted_flip_rate": margin_weighted_flip_penalty / total_samples,
            "mean_weighted_tau": float(np.mean(weighted_tau_scores)),
            "degenerate_samples": degenerate_count,
        }

    def fit_references(
        self, reference_paths: list[str], calib_dataloader, eval_dataloader
    ) -> tuple[dict, str]:
        """
        Computes clean divergence thresholds and the cache key.
        Returns: (Thresholds Dictionary, Cryptographic Cache Key)
        """
        self._verify_disjoint(calib_dataloader, eval_dataloader)

        q_format = QuantFormat.QOperator
        w_type = QuantType.QInt8
        a_type = QuantType.QUInt8

        cache_key = self.generate_cache_key(
            reference_paths, calib_dataloader, eval_dataloader, q_format, w_type, a_type
        )

        ref_flip_rates, ref_taus, ref_jsds = [], [], []

        for ref_path in reference_paths:
            fd, ref_int8 = tempfile.mkstemp(suffix=".onnx")
            os.close(fd)
            try:
                reader = CalibrationBatchReader(
                    calib_dataloader, ort.InferenceSession(ref_path).get_inputs()[0].name
                )
                quantize_static(
                    model_input=ref_path,
                    model_output=ref_int8,
                    calibration_data_reader=reader,
                    quant_format=q_format,
                    weight_type=w_type,
                    activation_type=a_type,
                )
                metrics = self.compute_divergence_metrics(ref_path, ref_int8, eval_dataloader)
                ref_flip_rates.append(metrics["margin_weighted_flip_rate"])
                ref_taus.append(metrics["mean_weighted_tau"])
                ref_jsds.append(metrics["mean_jsd"])
            finally:
                if os.path.exists(ref_int8):
                    os.remove(ref_int8)

        thresholds = {
            "max_clean_flip_rate": float(np.nextafter(max(ref_flip_rates), np.inf)),
            "min_clean_tau": float(np.nextafter(min(ref_taus), -np.inf)),
            "max_clean_jsd": float(np.nextafter(max(ref_jsds), np.inf)),
        }

        return thresholds, cache_key

    def evaluate_candidate(
        self, candidate_path: str, reference_thresholds: dict, calib_dataloader, eval_dataloader
    ) -> dict:
        """Evaluates a single candidate strictly against pre-computed reference thresholds."""
        self._verify_disjoint(calib_dataloader, eval_dataloader)

        fd, cand_int8 = tempfile.mkstemp(suffix=".onnx")
        os.close(fd)
        try:
            reader = CalibrationBatchReader(
                calib_dataloader, ort.InferenceSession(candidate_path).get_inputs()[0].name
            )
            quantize_static(
                model_input=candidate_path,
                model_output=cand_int8,
                calibration_data_reader=reader,
                quant_format=QuantFormat.QOperator,
                weight_type=QuantType.QInt8,
                activation_type=QuantType.QUInt8,
            )
            cand_metrics = self.compute_divergence_metrics(
                candidate_path, cand_int8, eval_dataloader
            )
        finally:
            if os.path.exists(cand_int8):
                os.remove(cand_int8)

        is_anomalous = (
            cand_metrics["margin_weighted_flip_rate"] > reference_thresholds["max_clean_flip_rate"]
            or cand_metrics["mean_weighted_tau"] < reference_thresholds["min_clean_tau"]
            or cand_metrics["mean_jsd"] > reference_thresholds["max_clean_jsd"]
        )

        return {
            "finding_type": "QUANTIZATION_FRAGILITY_COLLAPSE" if is_anomalous else "CLEAN",
            "candidate_metrics": cand_metrics,
            "disposition": "QUARANTINE" if is_anomalous else "ACCEPT",
        }

    def _softmax(self, x: np.ndarray) -> np.ndarray:
        e_x = np.exp(x - np.max(x, axis=1, keepdims=True))
        return e_x / e_x.sum(axis=1, keepdims=True)
