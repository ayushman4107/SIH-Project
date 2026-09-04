"""F2 architecture-matched per-layer weight-spectrum assurance."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.stats import wasserstein_distance

from sentinel.core.enums import Disposition, FindingType, ModuleStatus, Pillar, Severity
from sentinel.core.models import AssetLocator, Finding, MethodIdentity, ModuleAssessment, UnavailableMethod
from sentinel.core.normalizers import threshold_excess_confidence


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
    return {name: np.median(np.stack([reference[name] for reference in references]), axis=0) for name in signature}


def spectral_score(candidate: dict[str, np.ndarray], baseline: dict[str, np.ndarray]) -> tuple[float, dict[str, float]]:
    if _signature(candidate) != _signature(baseline):
        raise ValueError("candidate and reference tensor keys or shapes differ")
    distances = {name: float(wasserstein_distance(candidate[name], baseline[name])) for name in candidate}
    score = float(np.percentile(list(distances.values()), 95, method="linear"))
    return score, distances


@dataclass(frozen=True)
class ModelIntegrityResult:
    assessment: ModuleAssessment
    candidate_score: float | None
    threshold: float | None
    layer_distances: dict[str, float]
    calibration_scores: tuple[float, ...]


class ModelIntegrityModule:
    def analyze(
        self,
        *,
        candidate_state: dict[str, Any],
        reference_states: list[dict[str, Any]],
        architecture_id: str,
        candidate_id: str,
    ) -> ModelIntegrityResult:
        try:
            candidate = normalized_spectra(candidate_state)
        except ValueError as exc:
            if "non-finite" in str(exc):
                finding = Finding(
                    finding_type=FindingType.NON_FINITE_WEIGHT, pillar=Pillar.F2,
                    affected_asset=AssetLocator("model", candidate_id), severity=Severity.CRITICAL,
                    raw_score=None, decision_threshold="all analyzed weights finite", confidence=1.0,
                    confidence_normalizer="non_finite_policy_v1", human_readable_reason=str(exc),
                    evidence={"architecture_id": architecture_id}, method=MethodIdentity("weight_spectral_analysis", "1"),
                    recommended_disposition=Disposition.QUARANTINE,
                )
                return ModelIntegrityResult(ModuleAssessment(ModuleStatus.COMPLETED, (finding,), ("weight_spectral_analysis",), ()), None, None, {}, ())
            unavailable = UnavailableMethod("weight_spectral_analysis", str(exc))
            return ModelIntegrityResult(ModuleAssessment(ModuleStatus.UNAVAILABLE, (), (), (unavailable,)), None, None, {}, ())
        if len(reference_states) < 2:
            unavailable = UnavailableMethod("weight_spectral_analysis", "at least two same-architecture clean references are required")
            return ModelIntegrityResult(ModuleAssessment(ModuleStatus.UNAVAILABLE, (), (), (unavailable,)), None, None, {}, ())
        try:
            candidate_shapes = {
                name: tuple(matrix.shape) for name, matrix in analyzed_matrices(candidate_state).items()
            }
            reference_shapes = [
                {name: tuple(matrix.shape) for name, matrix in analyzed_matrices(state).items()}
                for state in reference_states
            ]
            if any(shapes != candidate_shapes for shapes in reference_shapes):
                raise ValueError("candidate/reference analyzed tensor keys or matrix shapes do not exactly match")
            references = [normalized_spectra(state) for state in reference_states]
            signature = _signature(candidate)
            if any(_signature(reference) != signature for reference in references):
                raise ValueError("candidate/reference analyzed keys or shapes do not exactly match")
            loo_scores = []
            for index, reference in enumerate(references):
                others = references[:index] + references[index + 1 :]
                score, _ = spectral_score(reference, median_spectra(others))
                loo_scores.append(score)
            threshold = float(np.nextafter(max(loo_scores), np.inf))
            score, distances = spectral_score(candidate, median_spectra(references))
        except ValueError as exc:
            unavailable = UnavailableMethod("weight_spectral_analysis", str(exc))
            return ModelIntegrityResult(ModuleAssessment(ModuleStatus.UNAVAILABLE, (), (), (unavailable,)), None, None, {}, ())
        findings: tuple[Finding, ...] = ()
        if score > threshold:
            confidence = threshold_excess_confidence(score, threshold)
            worst_layer = max(distances, key=distances.get)
            finding = Finding(
                finding_type=FindingType.WEIGHT_SPECTRAL_ANOMALY, pillar=Pillar.F2,
                affected_asset=AssetLocator("model", candidate_id, layer_name=worst_layer),
                severity=Severity.HIGH if confidence >= 0.95 else Severity.MEDIUM,
                raw_score=score, decision_threshold=threshold, confidence=confidence,
                confidence_normalizer="threshold_excess_v1",
                human_readable_reason="Model weight spectra exceed the maximum-clean-reference threshold.",
                evidence={"architecture_id": architecture_id, "layer_distances": distances, "calibration_scores": loo_scores, "worst_layer": worst_layer},
                method=MethodIdentity("weight_spectral_analysis", "1"),
                recommended_disposition=Disposition.QUARANTINE if confidence >= 0.95 else Disposition.REVIEW,
            )
            findings = (finding,)
        assessment = ModuleAssessment(ModuleStatus.COMPLETED, findings, ("weight_spectral_analysis",), ())
        return ModelIntegrityResult(assessment, score, threshold, distances, tuple(loo_scores))
