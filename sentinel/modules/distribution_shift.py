"""F4 Ledoit-Wolf Mahalanobis, predictive-entropy shift assurance, and GradNorm OOD."""

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


def temperature_scaled_logits(logits: np.ndarray, temperature: float = 1.5) -> np.ndarray:
    return np.asarray(logits, dtype=np.float32) / temperature


def stable_softmax(logits: np.ndarray, temperature: float = 1.5) -> np.ndarray:
    scaled = temperature_scaled_logits(logits, temperature)
    if scaled.ndim != 2 or not np.all(np.isfinite(scaled)):
        raise ValueError("logits must be a finite [sample, class] matrix")
    shifted = scaled - np.max(scaled, axis=1, keepdims=True)
    exponentials = np.exp(shifted, dtype=np.float32)
    return exponentials / np.sum(exponentials, axis=1, keepdims=True, dtype=np.float32)


def predictive_entropy(logits: np.ndarray, temperature: float = 1.5, epsilon: float = 1e-12) -> np.ndarray:
    probabilities = stable_softmax(logits, temperature)
    return -np.sum(probabilities * np.log(np.maximum(probabilities, epsilon)), axis=1)


def energy_score(logits: np.ndarray, temperature: float = 1.5) -> np.ndarray:
    scaled = temperature_scaled_logits(logits, temperature)
    if scaled.ndim != 2:
        raise ValueError("logits must be a 2D array")
    max_scaled = np.max(scaled, axis=1, keepdims=True)
    sum_exp = np.sum(np.exp(scaled - max_scaled), axis=1)
    return -temperature * (max_scaled.squeeze(1) + np.log(sum_exp))


def mahalanobis_distances(
    values: np.ndarray, location: np.ndarray, precision: np.ndarray
) -> np.ndarray:
    centered = np.asarray(values, dtype=np.float64) - location
    squared = np.einsum("ij,jk,ik->i", centered, precision, centered)
    return np.sqrt(np.maximum(squared, 0.0))


def is_detection_model(architecture_id: str, logits: np.ndarray) -> bool:
    if "yolo" in architecture_id.lower() or "det" in architecture_id.lower():
        return True
    if logits.ndim > 2:
        return True
    return False


def get_final_layer_weights(model: Any) -> tuple[Any, Any] | None:
    import torch
    if not isinstance(model, torch.nn.Module):
        return None
    final_layer = None
    for name, module in model.named_modules():
        if isinstance(module, torch.nn.Linear):
            final_layer = module
    if final_layer is not None:
        return final_layer.weight, final_layer.bias
    return None


def compute_gradnorm_vmap(embeddings: np.ndarray, weight: Any, bias: Any) -> np.ndarray:
    import torch
    from torch.func import grad, vmap

    w = weight.detach().clone()
    b = bias.detach().clone() if bias is not None else torch.zeros(w.shape[0], device=w.device)
    e = torch.tensor(embeddings, dtype=torch.float32, device=w.device)

    def head_loss(w_param, b_param, e_single):
        logits = torch.matmul(w_param, e_single) + b_param
        log_probs = torch.nn.functional.log_softmax(logits, dim=-1)
        return -log_probs.mean()

    grad_w_fn = grad(head_loss, argnums=0)
    per_sample_grads = vmap(grad_w_fn, in_dims=(None, None, 0))(w, b, e)
    
    # L1 norm flattened
    norms = torch.norm(per_sample_grads.reshape(e.shape[0], -1), p=1, dim=1)
    return norms.cpu().numpy()


@dataclass(frozen=True)
class DistributionShiftResult:
    assessment: ModuleAssessment
    characterization: str
    fused_risk: float
    component_scores: dict[str, float]
    thresholds: dict[str, float]
    model_dependency: str


class DistributionShiftModule:
    def __init__(
        self,
        *,
        joint_fpr: float = 0.05,
        temperature: float = 1.5,
        epsilon: float = 1e-12,
    ) -> None:
        # Bonferroni correction: alpha_individual = alpha_joint / 3
        self.alpha_individual = joint_fpr / 3.0
        self.ood_percentile = 1.0 - self.alpha_individual
        self.temperature = temperature
        self.epsilon = epsilon

    def analyze(
        self,
        *,
        reference_embeddings: np.ndarray,
        incoming_embeddings: np.ndarray,
        reference_logits: np.ndarray,
        incoming_logits: np.ndarray,
        model: Any = None,
        model_format: str = "pytorch",
        architecture_id: str = "unknown",
        incoming_ids: list[str] | None = None,
        model_suspicious: bool = False,
        projector: Any = None,
    ) -> DistributionShiftResult:
        
        findings: list[Finding] = []
        executed_methods = []
        unavailable_methods = []
        
        ids = incoming_ids or [str(index) for index in range(len(incoming_embeddings))]
        dependency = "depends_on_suspicious_model" if model_suspicious else "submitted_model_not_flagged_by_F2"

        # ---------------------------------------------------------
        # 1. Feature-Space Signal (Mahalanobis)
        # ---------------------------------------------------------
        reference = np.asarray(reference_embeddings, dtype=np.float64)
        incoming = np.asarray(incoming_embeddings, dtype=np.float64)
        estimator = LedoitWolf().fit(reference)
        ref_mahalanobis = mahalanobis_distances(reference, estimator.location_, estimator.precision_)
        inc_mahalanobis = mahalanobis_distances(incoming, estimator.location_, estimator.precision_)
        thresh_mahalanobis = float(np.quantile(ref_mahalanobis, self.ood_percentile))
        
        executed_methods.append("ledoit_wolf_mahalanobis")

        # ---------------------------------------------------------
        # 2. Energy/Output-Level Signal (Predictive Entropy)
        # ---------------------------------------------------------
        ref_entropy = predictive_entropy(reference_logits, self.temperature, self.epsilon)
        inc_entropy = predictive_entropy(incoming_logits, self.temperature, self.epsilon)
        thresh_entropy = float(np.quantile(ref_entropy, self.ood_percentile))
        
        executed_methods.append("predictive_entropy")

        # ---------------------------------------------------------
        # 3. Gradient Response Signal (GradNorm) or Energy Fallback
        # ---------------------------------------------------------
        inc_gradnorm = None
        thresh_gradnorm = None
        
        detection_model = is_detection_model(architecture_id, incoming_logits)
        
        if detection_model or model_format != "pytorch":
            # Fallback to Energy Score
            ref_energy = energy_score(reference_logits, self.temperature)
            inc_energy = energy_score(incoming_logits, self.temperature)
            thresh_gradnorm = float(np.quantile(ref_energy, self.ood_percentile))
            inc_gradnorm = inc_energy
            executed_methods.append("energy_score_fallback")
        else:
            weights = get_final_layer_weights(model) if model else None
            if weights is not None:
                try:
                    ref_gradnorm = compute_gradnorm_vmap(reference, weights[0], weights[1])
                    inc_gradnorm = compute_gradnorm_vmap(incoming, weights[0], weights[1])
                    
                    # GradNorm is typically lower for OOD. We want to find anomalies that fall below the threshold.
                    # So we use alpha_individual for the lower quantile.
                    thresh_gradnorm = float(np.quantile(ref_gradnorm, self.alpha_individual))
                    executed_methods.append("gradnorm_ood")
                except Exception as exc:
                    unavailable_methods.append(UnavailableMethod("gradnorm_ood", str(exc)))
            
            if inc_gradnorm is None:
                ref_energy = energy_score(reference_logits, self.temperature)
                inc_energy = energy_score(incoming_logits, self.temperature)
                thresh_gradnorm = float(np.quantile(ref_energy, self.ood_percentile))
                inc_gradnorm = inc_energy
                executed_methods.append("energy_score_fallback")

        # ---------------------------------------------------------
        # 4. Fusion and Routing
        # ---------------------------------------------------------
        max_fused_risk = 0.0
        characterization = "inconclusive"
        
        for i, sample_id in enumerate(ids):
            # Calculate risk ratios (distance from threshold, normalized)
            # Mahalanobis (higher is worse)
            risk_mah = inc_mahalanobis[i] / (thresh_mahalanobis + self.epsilon)
            
            # Entropy (higher is worse)
            risk_ent = inc_entropy[i] / (thresh_entropy + self.epsilon)
            
            # GradNorm (lower is worse) or Energy (higher is worse)
            if "gradnorm_ood" in executed_methods:
                risk_grad = thresh_gradnorm / (inc_gradnorm[i] + self.epsilon)
            else:
                risk_grad = inc_gradnorm[i] / (thresh_gradnorm + self.epsilon)
                
            fused_risk = float(max(risk_mah, risk_ent, risk_grad))
            max_fused_risk = max(max_fused_risk, fused_risk)
            
            if fused_risk > 1.0:
                severity = Severity.HIGH if fused_risk > 1.5 else Severity.MEDIUM
                disposition = Disposition.QUARANTINE if fused_risk > 1.5 else Disposition.REVIEW
                
                findings.append(
                    Finding(
                        finding_type=FindingType.OOD_SAMPLE,
                        pillar=Pillar.F4,
                        affected_asset=AssetLocator("sample", sample_id),
                        severity=severity,
                        raw_score=fused_risk,
                        decision_threshold=1.0,
                        confidence=min(1.0, 0.5 + 0.1 * fused_risk),
                        confidence_normalizer="fused_risk_max_v1",
                        human_readable_reason="Fused risk score exceeded the combined anomaly threshold.",
                        evidence={
                            "mahalanobis_risk": float(risk_mah),
                            "entropy_risk": float(risk_ent),
                            "gradient_risk": float(risk_grad),
                            "model_dependency": dependency,
                        },
                        method=MethodIdentity("fused_ood_detection", "1"),
                        recommended_disposition=disposition,
                    )
                )

        if max_fused_risk > 1.0:
            characterization = "possible_drift" if max_fused_risk <= 1.5 else "suspicious"

        assessment = ModuleAssessment(
            ModuleStatus.COMPLETED if not unavailable_methods else ModuleStatus.PARTIAL,
            tuple(findings),
            tuple(executed_methods),
            tuple(unavailable_methods),
        )
        
        return DistributionShiftResult(
            assessment=assessment,
            characterization=characterization,
            fused_risk=max_fused_risk,
            component_scores={
                "mean_mahalanobis": float(np.mean(inc_mahalanobis)),
                "mean_entropy": float(np.mean(inc_entropy)),
                "mean_gradient_or_energy": float(np.mean(inc_gradnorm)),
            },
            thresholds={
                "mahalanobis": thresh_mahalanobis,
                "entropy": thresh_entropy,
                "gradient_or_energy": thresh_gradnorm,
            },
            model_dependency=dependency,
        )
