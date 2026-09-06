"""F4 Ledoit-Wolf Mahalanobis and predictive-entropy shift assurance."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from sklearn.covariance import LedoitWolf

from sentinel.core.enums import Disposition, FindingType, ModuleStatus, Pillar, Severity
from sentinel.core.models import (
    AssetLocator,
    Finding,
    MethodIdentity,
    ModuleAssessment,
    UnavailableMethod,
)
from sentinel.core.normalizers import empirical_percentile, low_entropy_confidence


def stable_softmax(logits: np.ndarray) -> np.ndarray:
    values = np.asarray(logits, dtype=np.float32)
    if values.ndim != 2 or not np.all(np.isfinite(values)):
        raise ValueError("logits must be a finite [sample, class] matrix")
    shifted = values - np.max(values, axis=1, keepdims=True)
    exponentials = np.exp(shifted, dtype=np.float32)
    return exponentials / np.sum(exponentials, axis=1, keepdims=True, dtype=np.float32)


def predictive_entropy(logits: np.ndarray, epsilon: float = 1e-12) -> np.ndarray:
    probabilities = stable_softmax(logits)
    return -np.sum(probabilities * np.log(np.maximum(probabilities, epsilon)), axis=1)


def mahalanobis_distances(
    values: np.ndarray, location: np.ndarray, precision: np.ndarray
) -> np.ndarray:
    centered = np.asarray(values, dtype=np.float64) - location
    squared = np.einsum("ij,jk,ik->i", centered, precision, centered)
    return np.sqrt(np.maximum(squared, 0.0))


@dataclass(frozen=True)
class DistributionShiftResult:
    assessment: ModuleAssessment
    characterization: str
    entropy_ratio: float
    reference_entropy: float
    incoming_entropy: float
    model_dependency: str
    ood_threshold: float
    ood_pair_difficulty: str = "easy_baseline"


class DistributionShiftModule:
    def __init__(
        self,
        *,
        ood_percentile: float = 0.95,
        low_ratio: float = 0.7,
        high_ratio: float = 1.3,
        epsilon: float = 1e-12,
    ) -> None:
        self.ood_percentile = ood_percentile
        self.low_ratio = low_ratio
        self.high_ratio = high_ratio
        self.epsilon = epsilon

    def analyze(
        self,
        *,
        reference_embeddings: np.ndarray,
        incoming_embeddings: np.ndarray,
        reference_logits: np.ndarray,
        incoming_logits: np.ndarray,
        incoming_ids: list[str] | None = None,
        model_suspicious: bool = False,
        ood_pair_difficulty: str = "easy_baseline",
        projector: Any = None,
    ) -> DistributionShiftResult:
        reference = np.asarray(reference_embeddings, dtype=np.float64)
        incoming = np.asarray(incoming_embeddings, dtype=np.float64)
        if reference.ndim != 2 or incoming.ndim != 2 or reference.shape[1] != incoming.shape[1]:
            raise ValueError("reference and incoming embeddings must share feature dimensions")
        if (
            len(reference) < 2
            or len(incoming) < 1
            or not np.all(np.isfinite(reference))
            or not np.all(np.isfinite(incoming))
        ):
            raise ValueError("finite reference and incoming embeddings are required")
        if len(reference_logits) != len(reference) or len(incoming_logits) != len(incoming):
            raise ValueError("logit and embedding sample counts must match")
        estimator = LedoitWolf().fit(reference)
        reference_distances = mahalanobis_distances(
            reference, estimator.location_, estimator.precision_
        )
        incoming_distances = mahalanobis_distances(
            incoming, estimator.location_, estimator.precision_
        )
        threshold = float(np.quantile(reference_distances, self.ood_percentile))
        ids = incoming_ids or [str(index) for index in range(len(incoming))]
        if len(ids) != len(incoming):
            raise ValueError("incoming_ids length must match incoming embeddings")
        findings: list[Finding] = []
        for sample_id, distance in zip(ids, incoming_distances, strict=True):
            confidence = empirical_percentile(float(distance), reference_distances)
            if distance > threshold:
                findings.append(
                    Finding(
                        finding_type=FindingType.OOD_SAMPLE,
                        pillar=Pillar.F4,
                        affected_asset=AssetLocator("sample", sample_id),
                        severity=Severity.HIGH if confidence >= 0.95 else Severity.MEDIUM,
                        raw_score=float(distance),
                        decision_threshold=threshold,
                        confidence=confidence,
                        confidence_normalizer="reference_percentile_v1",
                        human_readable_reason=(
                            "Incoming embedding exceeds the reference Mahalanobis threshold."
                        ),
                        evidence={"reference_percentile": confidence},
                        method=MethodIdentity("ledoit_wolf_mahalanobis", "1"),
                        recommended_disposition=Disposition.QUARANTINE
                        if confidence >= 0.95
                        else Disposition.REVIEW,
                    )
                )

        # ---------------------------------------------------------
        # Synthetic Transformation Projector (Secondary Discriminator)
        # ---------------------------------------------------------
        projector_executed = False
        projector_unavailable = None
        if projector is not None:
            flagged_indices = [
                i for i, distance in enumerate(incoming_distances) if distance > threshold
            ]
            if flagged_indices:
                try:
                    import torch
                    z_anomalous = torch.tensor(
                        incoming[flagged_indices], dtype=torch.float32
                    )
                    proj_result = projector.evaluate_batch(z_anomalous)
                    is_orthogonal = proj_result["finding_type"] == "ORTHOGONAL_DRIFT_ANOMALY"
                    
                    ftype = (
                        FindingType.ORTHOGONAL_DRIFT_ANOMALY
                        if is_orthogonal
                        else FindingType.NATURAL_COVARIATE_DRIFT
                    )
                    
                    findings.append(
                        Finding(
                            finding_type=ftype,
                            pillar=Pillar.F4,
                            affected_asset=AssetLocator("inference_batch", "incoming"),
                            severity=Severity.CRITICAL if is_orthogonal else Severity.MEDIUM,
                            raw_score=proj_result["orthogonality_ratio"],
                            decision_threshold=str(projector.ortho_threshold),
                            confidence=0.95,  # High confidence from manifold projection
                            confidence_normalizer="fixed_v1",
                            human_readable_reason=(
                                "Adversarial orthogonal drift detected."
                                if is_orthogonal
                                else "Natural covariate drift detected."
                            ),
                            evidence={
                                "orthogonality_ratio": proj_result["orthogonality_ratio"],
                                "total_displacement": proj_result["total_displacement"],
                            },
                            method=MethodIdentity("synthetic_drift_projector", "1"),
                            recommended_disposition=(
                                Disposition.QUARANTINE if is_orthogonal else Disposition.REVIEW
                            ),
                        )
                    )
                    projector_executed = True
                except Exception as exc:
                    projector_unavailable = UnavailableMethod("synthetic_drift_projector", str(exc))
        # ---------------------------------------------------------
        reference_entropy = float(np.mean(predictive_entropy(reference_logits)))
        incoming_entropy = float(np.mean(predictive_entropy(incoming_logits)))
        ratio = incoming_entropy / max(reference_entropy, self.epsilon)
        dependency = (
            "depends_on_suspicious_model"
            if model_suspicious
            else "submitted_model_not_flagged_by_F2"
        )
        if ratio >= self.high_ratio:
            characterization = "possible_drift"
            findings.append(
                Finding(
                    finding_type=FindingType.POSSIBLE_DRIFT,
                    pillar=Pillar.F4,
                    affected_asset=AssetLocator("inference_batch", "incoming"),
                    severity=Severity.MEDIUM,
                    raw_score=ratio,
                    decision_threshold=self.high_ratio,
                    confidence=min(
                        1.0, 0.70 + 0.30 * min((ratio - self.high_ratio) / self.high_ratio, 1.0)
                    ),
                    confidence_normalizer="fixed_review_policy_v1",
                    human_readable_reason=(
                        "Mean predictive entropy increased by at least the configured ratio."
                    ),
                    evidence={
                        "reference_entropy": reference_entropy,
                        "incoming_entropy": incoming_entropy,
                        "model_dependency": dependency,
                    },
                    method=MethodIdentity("predictive_entropy_ratio", "1"),
                    recommended_disposition=Disposition.REVIEW,
                )
            )
        elif ratio <= self.low_ratio:
            characterization = "suspicious"
            confidence = low_entropy_confidence(ratio)
            findings.append(
                Finding(
                    finding_type=FindingType.SUSPICIOUS_ENTROPY_SHIFT,
                    pillar=Pillar.F4,
                    affected_asset=AssetLocator("inference_batch", "incoming"),
                    severity=Severity.HIGH if confidence >= 0.95 else Severity.MEDIUM,
                    raw_score=ratio,
                    decision_threshold=self.low_ratio,
                    confidence=confidence,
                    confidence_normalizer="low_entropy_ratio_v1",
                    human_readable_reason=(
                        "Mean predictive entropy decreased by at least the configured ratio."
                    ),
                    evidence={
                        "reference_entropy": reference_entropy,
                        "incoming_entropy": incoming_entropy,
                        "model_dependency": dependency,
                    },
                    method=MethodIdentity("predictive_entropy_ratio", "1"),
                    recommended_disposition=Disposition.QUARANTINE
                    if confidence >= 0.95
                    else Disposition.REVIEW,
                )
            )
        else:
            characterization = "inconclusive"
        executed_methods = ["ledoit_wolf_mahalanobis", "predictive_entropy_ratio"]
        if projector_executed:
            executed_methods.append("synthetic_drift_projector")
            
        unavailable_methods = []
        if projector_unavailable:
            unavailable_methods.append(projector_unavailable)
            
        assessment = ModuleAssessment(
            ModuleStatus.COMPLETED if not unavailable_methods else ModuleStatus.PARTIAL,
            tuple(findings),
            tuple(executed_methods),
            tuple(unavailable_methods),
        )
        return DistributionShiftResult(
            assessment,
            characterization,
            ratio,
            reference_entropy,
            incoming_entropy,
            dependency,
            threshold,
            ood_pair_difficulty,
        )
