"""F2 architecture-matched per-layer weight-spectrum assurance."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.stats import wasserstein_distance

from sentinel.core.enums import Disposition, FindingType, ModuleStatus, Pillar, Severity
from sentinel.core.models import (
    AssetLocator,
    Finding,
    MethodIdentity,
    ModuleAssessment,
    UnavailableMethod,
)
from sentinel.core.normalizers import threshold_excess_confidence
from sentinel.modules.activation_clustering import ActivationClusteringDetector

TENSOR_ELIGIBILITY = {
    "target_tensors": "weights only (name ends with 'weight')",
    "dimensions": "2D (linear) or 4D (conv2d)",
    "reshaping": "4D tensors are reshaped to 2D by flattening dimensions 1-3",
}


def _as_numpy(tensor: Any) -> np.ndarray:
    value = tensor
    if hasattr(value, "detach"):
        value = value.detach()
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "numpy"):
        value = value.numpy()
    return np.asarray(value)


def analyzed_matrices(state: dict[str, Any]) -> dict[str, np.ndarray]:
    matrices: dict[str, np.ndarray] = {}
    for name, tensor in state.items():
        array = _as_numpy(tensor)
        if not name.endswith("weight") or array.ndim not in {2, 4}:
            continue
        matrix = array.reshape(array.shape[0], -1) if array.ndim == 4 else array
        matrices[name] = np.asarray(matrix, dtype=np.float64)
    return matrices


def normalized_spectra(state: dict[str, Any], epsilon: float = 1e-12) -> dict[str, np.ndarray]:
    spectra: dict[str, np.ndarray] = {}
    for name, matrix in analyzed_matrices(state).items():
        if not np.all(np.isfinite(matrix)):
            raise ValueError(f"non-finite values in analyzed tensor {name}")
        singular_values = np.linalg.svd(matrix, compute_uv=False)
        denominator = max(float(np.sum(singular_values)), epsilon)
        spectra[name] = np.asarray(singular_values / denominator, dtype=np.float64)
    if not spectra:
        raise ValueError("model contains no eligible convolutional or linear weight tensors")
    return spectra


def _signature(spectra: dict[str, np.ndarray]) -> dict[str, tuple[int, ...]]:
    return {name: tuple(values.shape) for name, values in spectra.items()}


def median_spectra(references: list[dict[str, np.ndarray]]) -> dict[str, np.ndarray]:
    if not references:
        raise ValueError("at least one reference spectrum is required")
    signature = _signature(references[0])
    if any(_signature(reference) != signature for reference in references[1:]):
        raise ValueError("reference analyzed tensor keys or spectrum shapes differ")
    return {
        name: np.median(np.stack([reference[name] for reference in references]), axis=0)
        for name in signature
    }


def spectral_score(
    candidate: dict[str, np.ndarray], baseline: dict[str, np.ndarray]
) -> tuple[float, dict[str, float]]:
    if _signature(candidate) != _signature(baseline):
        raise ValueError("candidate and reference tensor keys or shapes differ")
    distances = {
        name: float(wasserstein_distance(candidate[name], baseline[name])) for name in candidate
    }
    score = float(np.percentile(list(distances.values()), 95, method="linear"))
    return score, distances


@dataclass(frozen=True)
class ModelIntegrityResult:
    assessment: ModuleAssessment
    candidate_score: float | None
    threshold: float | None
    layer_distances: dict[str, float]
    calibration_scores: tuple[float, ...]
    detection_margins: dict[str, float]
    threshold_margin_min: float | None
    calibration_stats: dict[str, Any]
    eligible_tensor_criteria: dict[str, Any]


class ModelIntegrityModule:
    def __init__(self, threshold_mode: str = "nextafter", regularized_k: float = 2.0):
        self.threshold_mode = threshold_mode
        self.regularized_k = regularized_k

    def analyze(
        self,
        *,
        candidate_state: dict[str, Any],
        reference_states: list[dict[str, Any]],
        architecture_id: str,
        candidate_id: str,
        candidate_adapter: Any = None,
        images_by_class: dict[int, Any] | None = None,
        sample_ids_by_class: dict[int, list[str]] | None = None,
    ) -> ModelIntegrityResult:
        try:
            candidate = normalized_spectra(candidate_state)
        except ValueError as exc:
            if "non-finite" in str(exc):
                finding = Finding(
                    finding_type=FindingType.NON_FINITE_WEIGHT,
                    pillar=Pillar.F2,
                    affected_asset=AssetLocator("model", candidate_id),
                    severity=Severity.CRITICAL,
                    raw_score=None,
                    decision_threshold="all analyzed weights finite",
                    confidence=1.0,
                    confidence_normalizer="non_finite_policy_v1",
                    human_readable_reason=str(exc),
                    evidence={"architecture_id": architecture_id},
                    method=MethodIdentity("weight_spectral_analysis", "1"),
                    recommended_disposition=Disposition.QUARANTINE,
                )
                return ModelIntegrityResult(
                    ModuleAssessment(
                        ModuleStatus.COMPLETED, (finding,), ("weight_spectral_analysis",), ()
                    ),
                    None,
                    None,
                    {},
                    (),
                    {},
                    None,
                    {},
                    TENSOR_ELIGIBILITY,
                )
            unavailable = UnavailableMethod("weight_spectral_analysis", str(exc))
            return ModelIntegrityResult(
                ModuleAssessment(ModuleStatus.UNAVAILABLE, (), (), (unavailable,)),
                None,
                None,
                {},
                (),
                {},
                None,
                {},
                TENSOR_ELIGIBILITY,
            )
        if len(reference_states) < 2:
            unavailable = UnavailableMethod(
                "weight_spectral_analysis",
                "at least two same-architecture clean references are required",
            )
            return ModelIntegrityResult(
                ModuleAssessment(ModuleStatus.UNAVAILABLE, (), (), (unavailable,)),
                None,
                None,
                {},
                (),
                {},
                None,
                {},
                TENSOR_ELIGIBILITY,
            )
        try:
            candidate_shapes = {
                name: tuple(matrix.shape)
                for name, matrix in analyzed_matrices(candidate_state).items()
            }
            reference_shapes = [
                {name: tuple(matrix.shape) for name, matrix in analyzed_matrices(state).items()}
                for state in reference_states
            ]
            if any(shapes != candidate_shapes for shapes in reference_shapes):
                raise ValueError(
                    "candidate/reference analyzed tensor keys or matrix shapes do not exactly match"
                )
            references = [normalized_spectra(state) for state in reference_states]
            signature = _signature(candidate)
            if any(_signature(reference) != signature for reference in references):
                raise ValueError("candidate/reference analyzed keys or shapes do not exactly match")
            loo_scores = []
            for index, reference in enumerate(references):
                others = references[:index] + references[index + 1 :]
                score, _ = spectral_score(reference, median_spectra(others))
                loo_scores.append(score)

            mu = float(np.mean(loo_scores))
            sigma = float(np.std(loo_scores))
            n_refs = len(loo_scores)

            if self.threshold_mode == "regularized":
                threshold = mu + self.regularized_k * sigma
            else:
                threshold = float(np.nextafter(max(loo_scores), np.inf))

            score, distances = spectral_score(candidate, median_spectra(references))

            calibration_stats = {
                "mean": mu,
                "std": sigma,
                "n": n_refs,
                "rule_of_three_upper_bound_fpr": 1.0 - (0.05 ** (1.0 / n_refs))
                if n_refs > 0
                else 1.0,
                "calibration_sample_size": n_refs,
                "calibration_confidence_note": (
                    f"Detection rate estimated from {n_refs} trials; "
                    "not statistically powered for high precision."
                ),
                "fpr_95ci_upper": 1.0 - (0.05 ** (1.0 / n_refs)) if n_refs > 0 else 1.0,
                "threshold_method": self.threshold_mode,
            }

        except ValueError as exc:
            unavailable = UnavailableMethod("weight_spectral_analysis", str(exc))
            return ModelIntegrityResult(
                ModuleAssessment(ModuleStatus.UNAVAILABLE, (), (), (unavailable,)),
                None,
                None,
                {},
                (),
                {},
                None,
                {},
                TENSOR_ELIGIBILITY,
            )
        findings: list[Finding] = []
        executed_methods: list[str] = []
        unavailable_methods: list[UnavailableMethod] = []
        detection_margins = {}
        threshold_margin_min = None

        margin = score - threshold
        if score > threshold:
            detection_margins[candidate_id] = margin
            threshold_margin_min = margin

            confidence = threshold_excess_confidence(score, threshold)
            worst_layer = max(distances, key=distances.get)
            finding = Finding(
                finding_type=FindingType.WEIGHT_SPECTRAL_ANOMALY,
                pillar=Pillar.F2,
                affected_asset=AssetLocator("model", candidate_id, layer_name=worst_layer),
                severity=Severity.HIGH if confidence >= 0.95 else Severity.MEDIUM,
                raw_score=score,
                decision_threshold=threshold,
                confidence=confidence,
                confidence_normalizer="threshold_excess_v1",
                human_readable_reason=(
                    "Model weight spectra exceed the maximum-clean-reference threshold."
                ),
                evidence={
                    "architecture_id": architecture_id,
                    "layer_distances": distances,
                    "calibration_scores": loo_scores,
                    "worst_layer": worst_layer,
                    "calibration_sample_size": calibration_stats["n"],
                    "calibration_confidence_note": calibration_stats["calibration_confidence_note"],
                    "fpr_95ci_upper": calibration_stats["fpr_95ci_upper"],
                    "threshold_method": calibration_stats["threshold_method"],
                    "detection_margins": [(candidate_id, margin)],
                },
                method=MethodIdentity("weight_spectral_analysis", "1"),
                recommended_disposition=Disposition.QUARANTINE
                if confidence >= 0.95
                else Disposition.REVIEW,
            )
            findings.append(finding)
            executed_methods.append("weight_spectral_analysis")
        else:
            calibration_stats["missed_model_margin"] = margin
            executed_methods.append("weight_spectral_analysis")

        if (
            candidate_adapter is not None
            and candidate_adapter.access_level == "white_box"
            and images_by_class is not None
            and sample_ids_by_class is not None
        ):
            try:
                detector = ActivationClusteringDetector()
                ac_findings = detector.run(
                    candidate_adapter.model, images_by_class, sample_ids_by_class
                )
                executed_methods.append("activation_clustering")
                for f in ac_findings:
                    findings.append(
                        Finding(
                            finding_type=FindingType.ACTIVATION_CLUSTER_ANOMALY,
                            pillar=Pillar.F2,
                            affected_asset=AssetLocator(
                                "model", candidate_id, class_id=str(f.class_id)
                            ),
                            severity=Severity.CRITICAL
                            if f.severity == "critical"
                            else Severity.HIGH,
                            raw_score=f.silhouette_score,
                            decision_threshold="silhouette >= 0.55",
                            confidence=f.confidence,
                            confidence_normalizer="silhouette_v1",
                            human_readable_reason=(
                                "Bimodal activation clustering detected for this class."
                            ),
                            evidence={
                                "layer_name": f.layer_name,
                                "minority_fraction": f.minority_fraction,
                                "suspected_sample_indices": f.suspected_sample_indices,
                            },
                            method=MethodIdentity("activation_clustering", "1"),
                            recommended_disposition=Disposition.QUARANTINE,
                        )
                    )
            except Exception as exc:
                unavailable_methods.append(UnavailableMethod("activation_clustering", str(exc)))
        else:
            unavailable_methods.append(
                UnavailableMethod("activation_clustering", "White-box model and images required")
            )

        # Elevate confidence if both methods flagged the same class?
        # In this simplistic integration, they are reported as independent findings.
        assessment = ModuleAssessment(
            ModuleStatus.COMPLETED
            if not unavailable_methods
            else (ModuleStatus.PARTIAL if executed_methods else ModuleStatus.UNAVAILABLE),
            tuple(findings),
            tuple(executed_methods),
            tuple(unavailable_methods),
        )
        return ModelIntegrityResult(
            assessment,
            score,
            threshold,
            distances,
            tuple(loo_scores),
            detection_margins,
            threshold_margin_min,
            calibration_stats,
            TENSOR_ELIGIBILITY,
        )
