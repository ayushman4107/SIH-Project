import hashlib

import numpy as np
import torch
import torch.nn.functional as F
from scipy.spatial.distance import jensenshannon
from scipy.stats import weightedtau
from torch.ao.quantization.quantize_fx import convert_fx, prepare_fx
from torch.utils.data import DataLoader


class PyTorchQuantizationProbe:
    # Methodology version: Includes SNR checking and FX Trace fail-safes
    METHODOLOGY_VERSION = "v1.3.0-pt-fx-snr-warning"

    def __init__(self):
        self.device = torch.device("cpu")  # Quantization evaluated strictly on CPU

    def _extract_sample_ids(self, dataloader) -> set[str]:
        if not isinstance(dataloader, DataLoader):
            raise TypeError(f"CRITICAL: Expected DataLoader, got {type(dataloader).__name__}.")

        dataset = getattr(dataloader, "dataset", None)
        if dataset is None:
            raise ValueError("CRITICAL: DataLoader does not expose a 'dataset' attribute.")

        sample_ids = getattr(dataset, "manifest_sample_ids", None)
        if sample_ids is None or len(sample_ids) == 0:
            raise ValueError("CRITICAL: Dataset does not expose 'manifest_sample_ids'.")
        return set(sample_ids)

    def _verify_disjoint(self, calib_dataloader, eval_dataloader):
        calib_ids = self._extract_sample_ids(calib_dataloader)
        eval_ids = self._extract_sample_ids(eval_dataloader)

        overlap = calib_ids.intersection(eval_ids)
        if overlap:
            raise ValueError(
                f"CRITICAL: {len(overlap)} sample_id(s) overlap between "
                "calib and eval sets."
            )

    @classmethod
    def generate_cache_key(
        cls, reference_paths: list[str], calib_dataloader, eval_dataloader
    ) -> str:
        calib_hash = getattr(calib_dataloader, "manifest_hash", None)
        eval_hash = getattr(eval_dataloader, "manifest_hash", None)

        if calib_hash is None or eval_hash is None:
            raise ValueError("CRITICAL: Dataloaders must expose 'manifest_hash'.")

        model_string = "".join(sorted(reference_paths))
        raw_key = f"{cls.METHODOLOGY_VERSION}_{model_string}_{calib_hash}_{eval_hash}_FX_QNNPACK"
        return hashlib.sha256(raw_key.encode()).hexdigest()

    def _quantize_model_fx(
        self, model: torch.nn.Module, calib_dataloader: DataLoader
    ) -> torch.nn.Module:
        """
        Attempts FX Graph Mode Static Quantization.
        Fails loud if symbolic tracing encounters arbitrary control flow.
        """
        model.eval()
        qconfig_mapping = torch.ao.quantization.get_default_qconfig_mapping("qnnpack")

        try:
            # FX tracing requires a dummy input tuple for shape inference
            dummy_input = next(iter(calib_dataloader))[0][0:1]
            prepared_model = prepare_fx(model, qconfig_mapping, example_inputs=(dummy_input,))

            # Calibrate ranges
            with torch.no_grad():
                for images, _ in calib_dataloader:
                    prepared_model(images.to(self.device))

            quantized_model = convert_fx(prepared_model)
            return quantized_model
        except Exception as e:
            # Catching generic Exception because FX TraceError and TorchScript mismatches
            # throw highly variable error types depending on the exact graph failure.
            raise RuntimeError(f"FX_TRACE_FAILURE: {str(e)}") from e

    @torch.no_grad()
    def compute_divergence_metrics(
        self, fp32_model: torch.nn.Module, int8_model: torch.nn.Module, eval_dataloader
    ) -> dict:
        fp32_model.eval()
        int8_model.eval()

        jsd_scores, weighted_tau_scores = [], []
        margin_weighted_flip_penalty = 0.0
        degenerate_count, total_samples = 0, 0

        for images, _ in eval_dataloader:
            images = images.to(self.device)
            total_samples += images.size(0)

            logits_fp32 = fp32_model(images)
            logits_int8 = int8_model(images)

            probs_fp32 = F.softmax(logits_fp32, dim=1).cpu().numpy()
            probs_int8 = F.softmax(logits_int8, dim=1).cpu().numpy()

            for i in range(images.size(0)):
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
        self, reference_models: list[torch.nn.Module], calib_dataloader, eval_dataloader
    ) -> tuple[dict, str]:
        self._verify_disjoint(calib_dataloader, eval_dataloader)
        cache_key = self.generate_cache_key(
            ["model_in_mem_list"], calib_dataloader, eval_dataloader
        )

        ref_flip_rates, ref_taus, ref_jsds = [], [], []

        for fp32_model in reference_models:
            fp32_model.to(self.device)
            try:
                int8_model = self._quantize_model_fx(fp32_model, calib_dataloader)
            except RuntimeError as e:
                return {"status": "UNAVAILABLE", "reason": str(e)}, cache_key

            metrics = self.compute_divergence_metrics(fp32_model, int8_model, eval_dataloader)
            ref_flip_rates.append(metrics["margin_weighted_flip_rate"])
            ref_taus.append(metrics["mean_weighted_tau"])
            ref_jsds.append(metrics["mean_jsd"])

        thresholds = {
            "status": "SUCCESS",
            "max_clean_flip_rate": float(np.nextafter(max(ref_flip_rates), np.inf)),
            "min_clean_tau": float(np.nextafter(min(ref_taus), -np.inf)),
            "max_clean_jsd": float(np.nextafter(max(ref_jsds), np.inf)),
        }

        # Determine Signal-to-Noise Ratio Status
        if thresholds["max_clean_flip_rate"] > 0.20 or thresholds["max_clean_jsd"] > 0.50:
            thresholds["snr_warning"] = True
        else:
            thresholds["snr_warning"] = False

        return thresholds, cache_key

    def evaluate_candidate(
        self,
        candidate_model: torch.nn.Module,
        reference_thresholds: dict,
        calib_dataloader,
        eval_dataloader,
    ) -> dict:
        if reference_thresholds.get("status") == "UNAVAILABLE":
            return {"finding_type": "UNAVAILABLE", "reason": "Reference models failed FX Tracing."}

        self._verify_disjoint(calib_dataloader, eval_dataloader)
        candidate_model.to(self.device)

        try:
            cand_int8 = self._quantize_model_fx(candidate_model, calib_dataloader)
        except RuntimeError as e:
            return {"finding_type": "UNAVAILABLE", "reason": str(e)}

        cand_metrics = self.compute_divergence_metrics(candidate_model, cand_int8, eval_dataloader)

        is_anomalous = (
            cand_metrics["margin_weighted_flip_rate"] > reference_thresholds["max_clean_flip_rate"]
            or cand_metrics["mean_weighted_tau"] < reference_thresholds["min_clean_tau"]
            or cand_metrics["mean_jsd"] > reference_thresholds["max_clean_jsd"]
        )

        result = {
            "finding_type": "QUANTIZATION_FRAGILITY_COLLAPSE" if is_anomalous else "CLEAN",
            "candidate_metrics": cand_metrics,
            "disposition": "QUARANTINE" if is_anomalous else "ACCEPT",
            "snr_warning": reference_thresholds.get("snr_warning", False),
        }

        if result["snr_warning"]:
            result["governance_note"] = (
                "LOW_STATISTICAL_POWER: Architecture naturally collapses under INT8. "
                "True positive signals may be masked."
            )

        return result
