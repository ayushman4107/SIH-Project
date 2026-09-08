"""
Approximates training-sample influence on a trusted, clean validation set
using gradient-dot-product influence (a first-order approximation of Koh &
Liang's influence functions, avoiding intractable Hessian inversion).
Flags training samples whose aggregate influence across the validation
set is strongly NEGATIVE (i.e., including this sample measurably HURTS
validation performance) as candidates for systematic mislabelling,
especially when negative-influence samples cluster around a shared
metadata attribute (region, sensor, batch, etc.).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from scipy.stats import chisquare


@dataclass
class InfluenceFinding:
    sample_id: str
    mean_influence_on_validation: float  # negative = harmful
    fraction_validation_hurt: float  # fraction of val samples this training point hurts
    severity: str
    confidence: float


class InfluenceFunctionDetector:
    def __init__(self, final_layer_name: str = "fc", harmful_threshold_percentile: float = 5.0):
        self.final_layer_name = final_layer_name
        self.harmful_threshold_percentile = harmful_threshold_percentile

    def _final_layer_gradient(self, model, final_layer, x, y) -> torch.Tensor:
        model.zero_grad(set_to_none=True)
        logits = model(x.unsqueeze(0))
        loss = F.cross_entropy(logits, y.unsqueeze(0))
        loss.backward()
        return final_layer.weight.grad.detach().clone().flatten()

    def run(
        self,
        model: nn.Module,
        train_images: torch.Tensor,
        train_labels: torch.Tensor,
        train_ids: list[str],
        val_images: torch.Tensor,
        val_labels: torch.Tensor,  # small TRUSTED clean holdout
        attribute_map: dict[str, str] | None = None,  # sample_id -> attribute (region, batch...)
    ) -> tuple[list[InfluenceFinding], dict]:
        final_layer = dict(model.named_modules())[self.final_layer_name]
        model.eval()

        # Precompute validation-set gradients once (reused against every train sample).
        val_grads = [
            self._final_layer_gradient(model, final_layer, vx, vy)
            for vx, vy in zip(val_images, val_labels, strict=False)
        ]

        findings = []
        influence_scores = []
        for i in range(train_images.shape[0]):
            g_train = self._final_layer_gradient(
                model, final_layer, train_images[i], train_labels[i]
            )
            per_val_influence = [float(torch.dot(g_train, gv)) for gv in val_grads]
            mean_influence = float(np.mean(per_val_influence))
            fraction_hurt = float(np.mean(np.array(per_val_influence) < 0))
            influence_scores.append(mean_influence)
            findings.append((train_ids[i], mean_influence, fraction_hurt))

        threshold = np.percentile(influence_scores, self.harmful_threshold_percentile)
        results = []
        for sample_id, mean_influence, fraction_hurt in findings:
            if mean_influence <= threshold:
                severity = "high" if mean_influence < threshold * 1.5 else "medium"
                results.append(
                    InfluenceFinding(
                        sample_id=sample_id,
                        mean_influence_on_validation=mean_influence,
                        fraction_validation_hurt=fraction_hurt,
                        severity=severity,
                        confidence=round(min(1.0, fraction_hurt), 4),
                    )
                )

        # Systematic-mislabelling-specific step: are harmful samples concentrated
        # around a shared attribute (e.g. region), rather than randomly scattered?
        concentration_report = {}
        if attribute_map:
            harmful_ids = {r.sample_id for r in results}
            attr_counts_harmful = defaultdict(int)
            attr_counts_total = defaultdict(int)
            for sid, attr in attribute_map.items():
                attr_counts_total[attr] += 1
                if sid in harmful_ids:
                    attr_counts_harmful[attr] += 1

            attrs = list(attr_counts_total.keys())
            observed = np.array([attr_counts_harmful.get(a, 0) for a in attrs], dtype=float)
            if observed.sum() >= 5 and len(attrs) >= 2:
                expected = observed.sum() * (
                    np.array([attr_counts_total[a] for a in attrs])
                    / sum(attr_counts_total.values())
                )
                _, p_value = chisquare(observed, expected)
                concentration_report = {
                    "attributes_tested": attrs,
                    "harmful_counts": dict(zip(attrs, observed.tolist(), strict=False)),
                    "concentration_p_value": float(p_value),
                    "systematic_pattern_detected": bool(p_value < 0.01),
                }

        return results, concentration_report
