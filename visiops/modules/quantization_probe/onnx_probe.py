import hashlib
import os
import tempfile
import numpy as np
import onnxruntime as ort
from onnxruntime.quantization import CalibrationDataReader, QuantFormat, QuantType, quantize_static
from scipy.spatial.distance import jensenshannon
from scipy.stats import weightedtau, binom
from torch.utils.data import DataLoader

class CalibrationBatchReader(CalibrationDataReader):
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
    METHODOLOGY_VERSION = "v7.0.0-dual-bounded-parametric"

    def __init__(self):
        pass

    def _extract_sample_ids(self, dataloader) -> list[str]:
        if not isinstance(dataloader, DataLoader):
            raise TypeError("Expected torch.utils.data.DataLoader")
        dataset = getattr(dataloader, "dataset", None)
        sample_ids = getattr(dataset, "manifest_sample_ids", None)
        if sample_ids is None or len(sample_ids) == 0:
            raise ValueError("Dataset missing 'manifest_sample_ids'")
        return list(sample_ids)

    def _verify_disjoint(self, calib_dataloader, eval_dataloader):
        calib_ids = set(self._extract_sample_ids(calib_dataloader))
        eval_ids = set(self._extract_sample_ids(eval_dataloader))
        overlap = calib_ids.intersection(eval_ids)
        if overlap:
            raise ValueError("CRITICAL: Calibration and Evaluation sets must be strictly disjoint.")

    @classmethod
    def generate_cache_key(cls, reference_paths: list[str], calib_dataloader, eval_dataloader, cand_precision: str) -> str:
        calib_hash = getattr(calib_dataloader, "manifest_hash", "calib_hash_fallback")
        eval_hash = getattr(eval_dataloader, "manifest_hash", "eval_hash_fallback")
        model_string = "".join(sorted(reference_paths))
        raw_key = f"{cls.METHODOLOGY_VERSION}_{model_string}_{calib_hash}_{eval_hash}_{cand_precision}"
        return hashlib.sha256(raw_key.encode()).hexdigest()

    def _softmax(self, x: np.ndarray) -> np.ndarray:
        e_x = np.exp(x - np.max(x, axis=1, keepdims=True))
        return e_x / e_x.sum(axis=1, keepdims=True)

    def extract_logits(self, model_path: str, dataloader: DataLoader) -> np.ndarray:
        session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
        input_name = session.get_inputs()[0].name
        all_logits = []
        for images, _ in dataloader:
            img_batch = images.numpy()
            logits = session.run(None, {input_name: img_batch})[0]
            all_logits.append(logits)
        return np.concatenate(all_logits, axis=0)

    def compute_sample_metrics(self, logits_target: np.ndarray, logits_ref: np.ndarray) -> dict:
        n_samples = logits_target.shape[0]
        probs_target = self._softmax(logits_target)
        probs_ref = self._softmax(logits_ref)
        
        jsd_array = np.zeros(n_samples)
        mse_array = np.zeros(n_samples)
        pred_target = np.argmax(probs_target, axis=1)
        pred_ref = np.argmax(probs_ref, axis=1)

        degenerate_count = 0
        for i in range(n_samples):
            jsd = jensenshannon(probs_target[i], probs_ref[i])
            if np.isnan(jsd) or np.isinf(jsd):
                jsd_array[i] = 1.0
                degenerate_count += 1
            else:
                jsd_array[i] = jsd
            
            mse_array[i] = np.mean((logits_target[i] - logits_ref[i])**2)
            
        return {
            "jsd": jsd_array,
            "mse": mse_array,
            "pred_target": pred_target,
            "pred_ref": pred_ref,
            "degenerate_count": degenerate_count
        }
        
    def _compute_class_flips(self, pred_target: np.ndarray, pred_ref: np.ndarray, num_classes: int) -> dict:
        flips = np.zeros(num_classes)
        samples = np.zeros(num_classes)
        for i in range(len(pred_ref)):
            c = pred_ref[i]
            samples[c] += 1
            if pred_target[i] != c:
                flips[c] += 1
        
        alpha, beta = 1.0, 10.0
        smoothed = (flips + alpha) / (samples + beta)
        return {"smoothed": smoothed, "flips": flips, "samples": samples}

    def _generate_parametric_baseline(self, ref_fp32: str, calib_dataloader, cand_precision: str) -> str:
        if cand_precision == "FP32":
            return ref_fp32
        elif cand_precision == "INT8":
            fd, ref_int8 = tempfile.mkstemp(suffix=".onnx")
            os.close(fd)
            reader = CalibrationBatchReader(calib_dataloader, ort.InferenceSession(ref_fp32).get_inputs()[0].name)
            quantize_static(
                model_input=ref_fp32,
                model_output=ref_int8,
                calibration_data_reader=reader,
                quant_format=QuantFormat.QOperator,
                weight_type=QuantType.QInt8,
                activation_type=QuantType.QUInt8,
            )
            return ref_int8
        else:
            # Proprietary / Unsupported format mismatch.
            raise NotImplementedError(f"Parametric baseline generation for {cand_precision} is unsupported.")

    def fit_references(self, reference_paths: list[str], calib_dataloader, eval_dataloader, cand_precision: str = "INT8") -> tuple[dict, str]:
        self._verify_disjoint(calib_dataloader, eval_dataloader)
        cache_key = self.generate_cache_key(reference_paths, calib_dataloader, eval_dataloader, cand_precision)
        
        ref_fp32 = reference_paths[0] # Simplification for V7 implementation script
        
        # V7 Parametric Baseline Generation
        target_ref_path = self._generate_parametric_baseline(ref_fp32, calib_dataloader, cand_precision)
        
        logits_fp32 = self.extract_logits(ref_fp32, eval_dataloader)
        logits_target = self.extract_logits(target_ref_path, eval_dataloader)
        
        if target_ref_path != ref_fp32 and os.path.exists(target_ref_path):
            os.remove(target_ref_path)

        metrics = self.compute_sample_metrics(logits_target, logits_fp32)
        
        num_classes = logits_fp32.shape[1]
        class_metrics = self._compute_class_flips(metrics["pred_target"], metrics["pred_ref"], num_classes)
        
        # Calculate dynamic class tolerances based on binomial bounds (simplified margin for demonstration)
        eps_c = np.zeros(num_classes)
        for c in range(num_classes):
            n = class_metrics["samples"][c]
            if n > 0:
                p = class_metrics["flips"][c] / n
                # Binomial standard deviation approx
                std_c = np.sqrt((p * (1 - p)) / n) if p > 0 else (1.0 / n)
                eps_c[c] = std_c * 3.0 + 0.05 # Dynamic + 5% floor
            else:
                eps_c[c] = 0.1 # Sparse class default
                
        thresholds = {
            "ref_jsd": metrics["jsd"],
            "ref_mse": metrics["mse"],
            "ref_smoothed_flips": class_metrics["smoothed"],
            "eps_c": eps_c,
            "eps_jsd_absolute": 0.5,
            "eps_mse_absolute": 10.0,
            "eps_sigma": 0.2,
            "eps_mu": 0.2
        }
        return thresholds, cache_key

    def evaluate_candidate(self, candidate_path: str, reference_thresholds: dict, calib_dataloader, eval_dataloader, ref_fp32: str) -> dict:
        self._verify_disjoint(calib_dataloader, eval_dataloader)
        
        logits_cand = self.extract_logits(candidate_path, eval_dataloader)
        logits_fp32 = self.extract_logits(ref_fp32, eval_dataloader)
        
        cand_metrics = self.compute_sample_metrics(logits_cand, logits_fp32)
        
        # ID-Mapped Deltas
        delta_jsd = cand_metrics["jsd"] - reference_thresholds["ref_jsd"]
        delta_mse = cand_metrics["mse"] - reference_thresholds["ref_mse"]
        
        mu_d = np.mean(delta_jsd)
        sigma_d = np.std(delta_jsd)
        
        z_jsd = np.zeros_like(delta_jsd)
        if sigma_d > 1e-6:
            z_jsd = (delta_jsd - mu_d) / sigma_d
            
        num_classes = logits_fp32.shape[1]
        cand_class_metrics = self._compute_class_flips(cand_metrics["pred_target"], cand_metrics["pred_ref"], num_classes)
        delta_flips = cand_class_metrics["smoothed"] - reference_thresholds["ref_smoothed_flips"]
        
        is_variance_inflation = sigma_d > reference_thresholds["eps_sigma"] or mu_d > reference_thresholds["eps_mu"]
        is_absolute_drift = np.max(delta_jsd) > reference_thresholds["eps_jsd_absolute"]
        is_z_spike = np.max(z_jsd) > 5.0
        is_mse_tampered = np.max(delta_mse) > reference_thresholds["eps_mse_absolute"]
        
        class_violations = delta_flips > reference_thresholds["eps_c"]
        is_targeted_class = np.any(class_violations)
        
        finding_type = "CLEAN"
        disposition = "ACCEPT"
        
        if is_variance_inflation or is_absolute_drift or is_z_spike or is_mse_tampered:
            finding_type = "QUANTIZATION_FRAGILITY_COLLAPSE"
            disposition = "QUARANTINE"
        elif is_targeted_class:
            finding_type = "ASYMMETRIC_CLASS_DEGRADATION"
            disposition = "REVIEW"

        return {
            "finding_type": finding_type,
            "disposition": disposition,
            "mean_jsd": float(np.mean(cand_metrics["jsd"])),
            "max_jsd_z": float(np.max(z_jsd)),
            "max_mse": float(np.max(cand_metrics["mse"])),
            "max_flip_delta": float(np.max(delta_flips)),
            "degenerate_samples": cand_metrics["degenerate_count"]
        }

from .contracts import QuantizationStatus, Stage2BResult, Stage2AResult

def run_stage_2b(probe: ONNXQuantizationProbe, candidate_path: str, reference_thresholds: dict, calib_dataloader, eval_dataloader, calibration_cache_key: str, ref_fp32: str) -> Stage2BResult:
    result = probe.evaluate_candidate(candidate_path, reference_thresholds, calib_dataloader, eval_dataloader, ref_fp32)
    
    status = QuantizationStatus.NORMAL_PRECISION_DRIFT
    if result["disposition"] == "QUARANTINE":
        status = QuantizationStatus.QUARANTINE
    elif result["disposition"] == "REVIEW":
        status = QuantizationStatus.REVIEW

    return Stage2BResult(
        status=status,
        mean_jsd=result["mean_jsd"],
        max_jsd_z=result["max_jsd_z"],
        max_mse=result["max_mse"],
        max_flip_delta=result["max_flip_delta"],
        degenerate_samples=result["degenerate_samples"],
        reference_thresholds={"redacted": True},
        probe_version=probe.METHODOLOGY_VERSION,
        calibration_cache_key=calibration_cache_key,
    )
