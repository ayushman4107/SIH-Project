"""
Detects backdoored classes via bimodal activation clustering at the
penultimate layer. Complements weight_spectral_analysis (which can be
evaded by spectrally-regularized attacks) by using a geometry-based,
not variance-based, separation criterion (ICA + k-means + silhouette).

Requires white-box access (forward-hook capable model). No retraining --
only forward passes on a frozen candidate model.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import torch
import torch.nn as nn
from sklearn.cluster import KMeans
from sklearn.decomposition import FastICA
from sklearn.metrics import silhouette_score


@dataclass
class ActivationClusterFinding:
    class_id: int
    layer_name: str
    silhouette_score: float
    minority_fraction: float
    suspected_sample_indices: list[int]
    severity: str
    confidence: float


class ActivationHookCapture:
    """Registers a forward hook on a named layer and captures its output
    for every forward pass, until removed."""

    def __init__(self, model: nn.Module, layer_name: str):
        self.activations: list[torch.Tensor] = []
        self._handle = None
        layer = dict(model.named_modules())[layer_name]
        self._handle = layer.register_forward_hook(self._hook)

    def _hook(self, module, inp, out):
        # Flatten any spatial dims (e.g. post-avgpool tensors are (B, C, 1, 1))
        self.activations.append(out.detach().flatten(start_dim=1).cpu())

    def clear(self):
        self.activations = []

    def remove(self):
        if self._handle is not None:
            self._handle.remove()


class ActivationClusteringDetector:
    def __init__(
        self,
        layer_name: str = "avgpool",
        ica_components: int = 6,
        silhouette_threshold: float = 0.55,
        min_minority_fraction: float = 0.02,
        max_minority_fraction: float = 0.30,
        min_class_samples: int = 20,
    ):
        self.layer_name = layer_name
        self.ica_components = ica_components
        self.silhouette_threshold = silhouette_threshold
        self.min_minority_fraction = min_minority_fraction
        self.max_minority_fraction = max_minority_fraction
        self.min_class_samples = min_class_samples

    @torch.no_grad()
    def _collect_activations(
        self, model: nn.Module, images: torch.Tensor, batch_size: int = 64
    ) -> np.ndarray:
        capture = ActivationHookCapture(model, self.layer_name)
        model.eval()
        for i in range(0, images.shape[0], batch_size):
            model(images[i : i + batch_size])
        acts = torch.cat(capture.activations, dim=0).numpy()
        capture.remove()
        return acts

    def run(
        self,
        model: nn.Module,
        images_by_class: dict[int, torch.Tensor],  # class_id -> (N_c, C, H, W)
        sample_ids_by_class: dict[int, list[str]],
    ) -> list[ActivationClusterFinding]:
        findings = []
        for cls, images in images_by_class.items():
            n = images.shape[0]
            if n < self.min_class_samples:
                continue  # report as unavailable at the orchestrator level, not here

            acts = self._collect_activations(model, images)
            n_components = min(self.ica_components, acts.shape[1], n - 1)

            # ICA, not PCA
            reduced = FastICA(
                n_components=n_components, random_state=42, max_iter=500, whiten="unit-variance"
            ).fit_transform(acts)

            kmeans = KMeans(n_clusters=2, n_init=10, random_state=42).fit(reduced)
            labels = kmeans.labels_
            try:
                score = silhouette_score(reduced, labels)
            except ValueError:
                continue

            counts = np.bincount(labels)
            minority_fraction = float(counts.min()) / n

            if (
                score >= self.silhouette_threshold
                and self.min_minority_fraction <= minority_fraction <= self.max_minority_fraction
            ):
                minority_cluster = int(np.argmin(counts))
                suspected = [i for i, lbl in enumerate(labels) if lbl == minority_cluster]
                severity = "critical" if score > 0.75 else "high"
                findings.append(
                    ActivationClusterFinding(
                        class_id=cls,
                        layer_name=self.layer_name,
                        silhouette_score=float(score),
                        minority_fraction=minority_fraction,
                        suspected_sample_indices=suspected,
                        severity=severity,
                        confidence=round(min(1.0, score), 4),
                    )
                )
        return findings
