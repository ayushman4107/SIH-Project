"""
Adapts federated-learning gradient-clustering defenses to a single frozen
model. Computes per-sample final-layer loss gradients and flags samples
whose gradient direction is anomalously misaligned with their nominal
class's centroid gradient -- a signature of label flipping. Requires
white-box access (backward-pass capable model); no optimizer steps are
ever applied to the candidate model.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F


@dataclass
class GradientClusterFinding:
    sample_id: str
    nominal_class: int
    cosine_to_class_centroid: float
    nearest_alternate_class: int
    cosine_to_alternate_centroid: float
    severity: str
    confidence: float


class GradientClusteringDetector:
    def __init__(
        self,
        final_layer_name: str = "fc",
        anomaly_index_threshold: float = 2.5,  # MAD-multiples below centroid alignment
    ):
        self.final_layer_name = final_layer_name
        self.anomaly_index_threshold = anomaly_index_threshold

    def _per_sample_final_layer_gradient(
        self, model: nn.Module, x: torch.Tensor, y: torch.Tensor
    ) -> torch.Tensor:
        """
        Computes d(loss)/d(final_layer.weight) for a SINGLE sample without
        ever calling optimizer.step() -- this is pure gradient computation
        for analysis, not training.
        """
        final_layer = dict(model.named_modules())[self.final_layer_name]
        model.zero_grad(set_to_none=True)
        logits = model(x.unsqueeze(0))
        loss = F.cross_entropy(logits, y.unsqueeze(0))
        loss.backward()
        grad = final_layer.weight.grad.detach().clone().flatten()
        return grad

    def run(
        self,
        model: nn.Module,
        images_by_class: dict[int, torch.Tensor],
        sample_ids_by_class: dict[int, list[str]],
        all_class_ids: list[int],
    ) -> list[GradientClusterFinding]:
        model.eval()  # eval mode for BN/dropout consistency; gradients still flow

        # Step 1: compute every sample's per-sample final-layer gradient, keyed by class.
        gradients_by_class: dict[int, list[torch.Tensor]] = {c: [] for c in all_class_ids}
        for cls, images in images_by_class.items():
            y = torch.tensor(cls)
            for img in images:
                g = self._per_sample_final_layer_gradient(model, img, y)
                gradients_by_class[cls].append(g)

        # Step 2: compute each class's centroid gradient direction (normalized mean).
        centroids: dict[int, torch.Tensor] = {}
        for cls, grads in gradients_by_class.items():
            if not grads:
                continue
            stacked = torch.stack(grads)
            centroid = stacked.mean(dim=0)
            centroids[cls] = centroid / (centroid.norm() + 1e-12)

        # Step 3: for each sample, measure cosine alignment to its OWN class centroid
        # and to every OTHER class's centroid; flag samples that align better elsewhere.
        findings = []
        for cls, grads in gradients_by_class.items():
            own_centroid = centroids.get(cls)
            if own_centroid is None:
                continue
            own_cosines = [float(torch.dot(g / (g.norm() + 1e-12), own_centroid)) for g in grads]
            own_cosines_arr = np.array(own_cosines)
            median = np.median(own_cosines_arr)
            mad = np.median(np.abs(own_cosines_arr - median)) + 1e-8

            for i, (g, own_cos) in enumerate(zip(grads, own_cosines, strict=False)):
                anomaly_index = (median - own_cos) / mad  # low own-class alignment = outlier
                if anomaly_index < self.anomaly_index_threshold:
                    continue

                # Find which OTHER class this sample's gradient actually aligns best with.
                g_norm = g / (g.norm() + 1e-12)
                alt_scores = {
                    c: float(torch.dot(g_norm, cen)) for c, cen in centroids.items() if c != cls
                }
                if not alt_scores:
                    continue
                best_alt_class = max(alt_scores, key=alt_scores.get)
                best_alt_cos = alt_scores[best_alt_class]

                if best_alt_cos > own_cos:  # aligns better with a DIFFERENT class
                    severity = "critical" if anomaly_index > 4.0 else "high"
                    findings.append(
                        GradientClusterFinding(
                            sample_id=sample_ids_by_class[cls][i],
                            nominal_class=cls,
                            cosine_to_class_centroid=own_cos,
                            nearest_alternate_class=best_alt_class,
                            cosine_to_alternate_centroid=best_alt_cos,
                            severity=severity,
                            confidence=round(min(1.0, float(anomaly_index / 6.0)), 4),
                        )
                    )
        return findings
