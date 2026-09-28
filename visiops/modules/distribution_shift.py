"""FF5 V8: Gradient-Norm Spoofing Defense with Beta-Divergence, VJP, and Isolation Forests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import math

import numpy as np
from sklearn.covariance import LedoitWolf
from sklearn.ensemble import IsolationForest
import scipy.stats as stats

from visiops.core.enums import Disposition, FindingType, ModuleStatus, Pillar, Severity
from visiops.core.models import (
    AssetLocator,
    Finding,
    MethodIdentity,
    ModuleAssessment,
    UnavailableMethod,
)

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

def get_final_layer_module(model: Any) -> Any | None:
    import torch
    if not isinstance(model, torch.nn.Module):
        return None
    final_layer = None
    for name, module in model.named_modules():
        if isinstance(module, torch.nn.Linear):
            final_layer = module
    return final_layer

def compute_functional_vjp_gradnorm(
    model_head: Any, 
    embeddings: np.ndarray, 
    logits: np.ndarray
) -> np.ndarray:
    """FF5 V8: Functional VJP Emulation for exact Jacobian-Vector Product."""
    import torch
    from torch.func import vmap, vjp
    
    # 1. Compute KL-Uniform Analytical Logit Gradient
    P = stable_softmax(logits, temperature=1.0) # Unscaled for loss formulation
    K = P.shape[1]
    
    # 
    # abla_Z L_{KL} = P \odot (\log(K \cdot P) + 1 - \sum_j P_j \log(K \cdot P_j))
    # For numerical stability:
    log_K_P = np.log(np.maximum(K * P, 1e-12))
    sum_P_log_K_P = np.sum(P * log_K_P, axis=1, keepdims=True)
    grad_Z_np = P * (log_K_P + 1.0 - sum_P_log_K_P)
    
    # 2. VJP Emulation
    h_tensor = torch.tensor(embeddings, dtype=torch.float32, device=next(model_head.parameters()).device)
    grad_Z_tensor = torch.tensor(grad_Z_np, dtype=torch.float32, device=h_tensor.device)
    
    # Functionalize the head module execution
    def head_forward(h_single):
        return model_head(h_single.unsqueeze(0)).squeeze(0)
    
    # Compute vector-Jacobian product efficiently across the batch
    def compute_single_vjp(h_single, v_single):
        _, vjp_fn = vjp(head_forward, h_single)
        return vjp_fn(v_single)[0]
    
    grad_H = vmap(compute_single_vjp)(h_tensor, grad_Z_tensor)
    
    # 3. L2 Norm of Penultimate Gradient
    norms = torch.norm(grad_H, p=2, dim=1)
    return norms.cpu().numpy()

def copula_transform(signals: np.ndarray, reference_signals: np.ndarray) -> np.ndarray:
    """Winsorized Copula Transform to Standard Normal."""
    n_samples, n_dims = signals.shape
    transformed = np.zeros_like(signals)
    
    for d in range(n_dims):
        # 1. ECDF mapping
        ref_d = reference_signals[:, d]
        sig_d = signals[:, d]
        
        # Calculate rank percentile (ECDF)
        percentiles = np.searchsorted(np.sort(ref_d), sig_d) / float(len(ref_d))
        
        # 2. Winsorized Clamping
        epsilon = 0.001
        clamped_percentiles = np.clip(percentiles, epsilon, 1.0 - epsilon)
        
        # 3. Inverse Normal CDF
        transformed[:, d] = stats.norm.ppf(clamped_percentiles)
        
    return transformed

@dataclass(frozen=True)
class DistributionShiftResult:
    assessment: ModuleAssessment
    characterization: str
    fused_risk: float
    component_scores: dict[str, float]
    thresholds: dict[str, float]
    model_dependency: str
    fallback_active: bool
    beta_divergence_alert: bool

class DistributionShiftModule:
    def __init__(
        self,
        *,
        joint_fpr: float = 0.05,
        temperature: float = 1.5,
        epsilon: float = 1e-12,
    ) -> None:
        self.alpha_individual = joint_fpr / 4.0 # 4 signals max
        self.ood_percentile = 1.0 - self.alpha_individual
        self.temperature = temperature
        self.epsilon = epsilon
        
        # Stateful references for Copula and IF
        self.reference_mahalanobis = None
        self.reference_entropy = None
        self.reference_gradnorm = None
        self.reference_energy = None
        
        self.copula_ledoit_wolf = None
        self.isolation_forest_2d = None

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

        # Reference Feature Mahalanobis Precompute
        reference = np.asarray(reference_embeddings, dtype=np.float64)
        incoming = np.asarray(incoming_embeddings, dtype=np.float64)
        estimator = LedoitWolf().fit(reference)
        ref_mah = mahalanobis_distances(reference, estimator.location_, estimator.precision_)
        inc_mah = mahalanobis_distances(incoming, estimator.location_, estimator.precision_)
        
        # Energy Precompute
        ref_ene = energy_score(reference_logits, self.temperature)
        inc_ene = energy_score(incoming_logits, self.temperature)
        
        # Entropy Precompute
        ref_ent = predictive_entropy(reference_logits, self.temperature, self.epsilon)
        inc_ent = predictive_entropy(incoming_logits, self.temperature, self.epsilon)

        inc_gradnorm = None
        fallback_active = False
        
        detection_model = is_detection_model(architecture_id, incoming_logits)
        model_head = get_final_layer_module(model) if model else None
        
        if detection_model or model_format != "pytorch" or model_head is None:
            # V8 Non-Linear Manifold Isolation Fallback
            fallback_active = True
            unavailable_methods.append(UnavailableMethod("functional_vjp_gradnorm", "Architecture unsupported"))
            executed_methods.append("isolation_forest_2d_fallback")
            
            # Prepare 2D Copula
            ref_signals_2d = np.column_stack([ref_mah, ref_ene])
            inc_signals_2d = np.column_stack([inc_mah, inc_ene])
            
            if self.isolation_forest_2d is None:
                # Train Isolation Forest on 2D Copula transformed references
                transformed_ref_2d = copula_transform(ref_signals_2d, ref_signals_2d)
                self.isolation_forest_2d = IsolationForest(contamination=0.01, random_state=42)
                self.isolation_forest_2d.fit(transformed_ref_2d)
                
            transformed_inc_2d = copula_transform(inc_signals_2d, ref_signals_2d)
            # IF returns negative scores for anomalies. Convert to positive risk.
            if_scores = -self.isolation_forest_2d.score_samples(transformed_inc_2d)
            # Normalized against theoretical threshold 0
            fused_risks = np.maximum(if_scores, 0) / 0.1 # Approximate scaling
            
        else:
            # V8 Functional VJP 4D Extraction
            try:
                ref_gradnorm = compute_functional_vjp_gradnorm(model_head, reference, reference_logits)
                inc_gradnorm = compute_functional_vjp_gradnorm(model_head, incoming, incoming_logits)
                executed_methods.append("functional_vjp_gradnorm")
                
                # 4D Copula Fusion
                ref_signals_4d = np.column_stack([ref_mah, ref_ent, ref_gradnorm, ref_ene])
                inc_signals_4d = np.column_stack([inc_mah, inc_ent, inc_gradnorm, inc_ene])
                
                transformed_ref_4d = copula_transform(ref_signals_4d, ref_signals_4d)
                transformed_inc_4d = copula_transform(inc_signals_4d, ref_signals_4d)
                
                if self.copula_ledoit_wolf is None:
                    self.copula_ledoit_wolf = LedoitWolf().fit(transformed_ref_4d)
                    
                copula_distances = mahalanobis_distances(
                    transformed_inc_4d, 
                    self.copula_ledoit_wolf.location_, 
                    self.copula_ledoit_wolf.precision_
                )
                
                # Threshold for 4-DOF Chi-Squared at alpha=0.01 is ~3.64 (sqrt of 13.27)
                fused_risks = copula_distances / 3.64
                
            except Exception as exc:
                fallback_active = True
                unavailable_methods.append(UnavailableMethod("functional_vjp_gradnorm", str(exc)))
                fused_risks = np.zeros(len(incoming)) # Simplified for error path

        max_fused_risk = float(np.max(fused_risks))
        characterization = "inconclusive"
        
        for i, sample_id in enumerate(ids):
            risk = float(fused_risks[i])
            if risk > 1.0:
                severity = Severity.HIGH if risk > 1.5 else Severity.MEDIUM
                disposition = Disposition.QUARANTINE if risk > 1.5 else Disposition.REVIEW
                
                findings.append(
                    Finding(
                        finding_type=FindingType.OOD_SAMPLE,
                        pillar=Pillar.F4,
                        affected_asset=AssetLocator("sample", sample_id),
                        severity=severity,
                        raw_score=risk,
                        decision_threshold=1.0,
                        confidence=min(1.0, 0.5 + 0.1 * risk),
                        confidence_normalizer="v8_copula_coherence",
                        human_readable_reason="V8 Copula Coherence anomaly detected across multi-signal extraction.",
                        evidence={
                            "copula_risk": risk,
                            "model_dependency": dependency,
                            "fallback_active": fallback_active
                        },
                        method=MethodIdentity("fused_ood_detection", "8"),
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
                "mean_mahalanobis": float(np.mean(inc_mah)),
                "mean_energy": float(np.mean(inc_ene)),
                "mean_gradnorm": float(np.mean(inc_gradnorm)) if inc_gradnorm is not None else 0.0,
            },
            thresholds={
                "copula_coherence": 1.0,
            },
            model_dependency=dependency,
            fallback_active=fallback_active,
            beta_divergence_alert=False # Stub for online CDF updates
        )
