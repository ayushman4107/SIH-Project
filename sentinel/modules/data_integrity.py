"""F1 label, duplicate, outlier, and source-concentration assurance."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any

import numpy as np

from sentinel.adapters.datasets import DatasetManifest
from sentinel.core.enums import Disposition, FindingType, ModuleStatus, Pillar, Severity
from sentinel.core.models import (
    AssetLocator,
    Finding,
    MethodIdentity,
    ModuleAssessment,
    UnavailableMethod,
)
from sentinel.core.normalizers import (
    cosine_confidence,
    empirical_percentile,
    generic_disposition,
    label_quality_confidence,
    phash_confidence,
)


@dataclass(frozen=True)
class DataIntegrityConfig:
    seed: int = 42
    folds: int = 5
    phash_distance: int = 8
    cosine_threshold: float = 0.95
    cosine_neighbors: int = 10
    neighbor_chunk_size: int = 1024
    outlier_percentile: float = 0.95
    isolation_contamination: str | float = "auto"
    source_min_anomalies: int = 5
    source_p_value: float = 0.01
    source_rate_multiplier: float = 2.0


class _BKNode:
    def __init__(self, value: int, index: int) -> None:
        self.value = value
        self.indices = [index]
        self.children: dict[int, _BKNode] = {}

    def insert(self, value: int, index: int) -> None:
        distance = (self.value ^ value).bit_count()
        if distance == 0:
            self.indices.append(index)
            return
        child = self.children.get(distance)
        if child is None:
            self.children[distance] = _BKNode(value, index)
        else:
            child.insert(value, index)

    def query(self, value: int, radius: int, result: list[tuple[int, int]]) -> None:
        distance = (self.value ^ value).bit_count()
        if distance <= radius:
            result.extend((index, distance) for index in self.indices)
        for edge, child in self.children.items():
            if distance - radius <= edge <= distance + radius:
                child.query(value, radius, result)


def _phash_pairs(manifest: DatasetManifest, radius: int) -> dict[tuple[int, int], dict[str, Any]]:
    try:
        import imagehash
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Pillow and ImageHash are required for pHash detection") from exc
    root: _BKNode | None = None
    pairs: dict[tuple[int, int], dict[str, Any]] = {}
    for index, sample in enumerate(manifest.samples):
        with Image.open(sample.image_path) as image:
            value = int(str(imagehash.phash(image.convert("RGB"), hash_size=8)), 16)
        if root is not None:
            matches: list[tuple[int, int]] = []
            root.query(value, radius, matches)
            for other, distance in matches:
                pairs[(other, index)] = {"phash_distance": distance}
            root.insert(value, index)
        else:
            root = _BKNode(value, index)
    return pairs


def _cosine_pairs(
    embeddings: np.ndarray, threshold: float, k: int, chunk_size: int
) -> dict[tuple[int, int], dict[str, Any]]:
    vectors = np.asarray(embeddings, dtype=np.float64)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    normalized = np.divide(vectors, norms, out=np.zeros_like(vectors), where=norms > 0)
    count = len(normalized)
    pairs: dict[tuple[int, int], dict[str, Any]] = {}
    neighbors = min(k, max(count - 1, 0))
    if neighbors == 0:
        return pairs
    for start in range(0, count, chunk_size):
        stop = min(start + chunk_size, count)
        similarities = normalized[start:stop] @ normalized.T
        similarities[np.arange(stop - start), np.arange(start, stop)] = -np.inf
        candidates = np.argpartition(similarities, -neighbors, axis=1)[:, -neighbors:]
        for row, indices in enumerate(candidates):
            left = start + row
            for right in indices:
                similarity = float(similarities[row, right])
                if similarity >= threshold:
                    pair = (min(left, int(right)), max(left, int(right)))
                    pairs[pair] = {"cosine_similarity": similarity}
    return pairs


def _duplicate_findings(
    manifest: DatasetManifest, embeddings: np.ndarray, config: DataIntegrityConfig
) -> tuple[list[Finding], set[int]]:
    pairs = _phash_pairs(manifest, config.phash_distance)
    for pair, evidence in _cosine_pairs(
        embeddings, config.cosine_threshold, config.cosine_neighbors, config.neighbor_chunk_size
    ).items():
        pairs.setdefault(pair, {}).update(evidence)
    adjacency: dict[int, set[int]] = defaultdict(set)
    for left, right in pairs:
        adjacency[left].add(right)
        adjacency[right].add(left)
    findings: list[Finding] = []
    affected: set[int] = set()
    pending = set(adjacency)
    while pending:
        first = pending.pop()
        component = {first}
        queue = deque([first])
        while queue:
            current = queue.popleft()
            for neighbor in adjacency[current]:
                if neighbor not in component:
                    component.add(neighbor)
                    pending.discard(neighbor)
                    queue.append(neighbor)
        affected.update(component)
        evidence_pairs = []
        confidences = []
        for (left, right), evidence in sorted(pairs.items()):
            if left in component and right in component:
                row = {
                    "left": manifest.samples[left].sample_id,
                    "right": manifest.samples[right].sample_id,
                    **evidence,
                }
                evidence_pairs.append(row)
                if "phash_distance" in evidence:
                    confidences.append(phash_confidence(evidence["phash_distance"]))
                if "cosine_similarity" in evidence:
                    confidences.append(cosine_confidence(evidence["cosine_similarity"]))
        confidence = max(confidences)
        sample_ids = tuple(sorted(manifest.samples[index].sample_id for index in component))
        findings.append(
            Finding(
                finding_type=FindingType.NEAR_DUPLICATE,
                pillar=Pillar.F1,
                affected_asset=AssetLocator(
                    "duplicate_cluster", "duplicate:" + sample_ids[0], sample_ids=sample_ids
                ),
                severity=Severity.HIGH if confidence >= 0.95 else Severity.MEDIUM,
                raw_score=max(
                    (row.get("cosine_similarity", 0.0) for row in evidence_pairs), default=None
                ),
                decision_threshold=(
                    f"pHash<={config.phash_distance} or cosine>={config.cosine_threshold}"
                ),
                confidence=confidence,
                confidence_normalizer="max_duplicate_evidence_v1",
                human_readable_reason="Images form a connected near-duplicate cluster.",
                evidence={"pairs": evidence_pairs},
                method=MethodIdentity("phash_cosine_duplicates", "1"),
                recommended_disposition=generic_disposition(confidence),
            )
        )
    return findings, affected


def _label_findings(
    manifest: DatasetManifest, embeddings: np.ndarray, config: DataIntegrityConfig
) -> tuple[list[Finding], set[int]]:
    from cleanlab.filter import find_label_issues
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedKFold
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    labels = np.array([sample.label for sample in manifest.samples], dtype=np.int64)
    counts = np.bincount(labels, minlength=manifest.num_classes)
    if np.any(counts[counts > 0] < config.folds):
        raise ValueError("each represented class requires at least five samples for OOF analysis")
    probabilities = np.zeros((len(labels), manifest.num_classes), dtype=np.float64)
    fold_ids = np.empty(len(labels), dtype=np.int64)
    splitter = StratifiedKFold(n_splits=config.folds, shuffle=True, random_state=config.seed)
    for fold, (train, held_out) in enumerate(splitter.split(embeddings, labels)):
        pipeline = make_pipeline(
            StandardScaler(),
            LogisticRegression(class_weight="balanced", max_iter=1000, random_state=config.seed),
        )
        pipeline.fit(embeddings[train], labels[train])
        fold_probabilities = pipeline.predict_proba(embeddings[held_out])
        probabilities[held_out[:, None], pipeline[-1].classes_[None, :]] = fold_probabilities
        fold_ids[held_out] = fold
    ranked = find_label_issues(
        labels=labels, pred_probs=probabilities, return_indices_ranked_by="self_confidence"
    )
    findings: list[Finding] = []
    affected: set[int] = set()
    for index in np.asarray(ranked, dtype=int):
        quality = float(probabilities[index, labels[index]])
        confidence = label_quality_confidence(quality)
        suggested = int(np.argmax(probabilities[index]))
        affected.add(int(index))
        findings.append(
            Finding(
                finding_type=FindingType.LABEL_ERROR,
                pillar=Pillar.F1,
                affected_asset=AssetLocator(
                    "sample",
                    manifest.samples[index].sample_id,
                    source_id=manifest.samples[index].source_id,
                ),
                severity=Severity.HIGH if confidence >= 0.95 else Severity.MEDIUM,
                raw_score=quality,
                decision_threshold=0.70,
                confidence=confidence,
                confidence_normalizer="cleanlab_inverse_quality_v1",
                human_readable_reason=(
                    "Out-of-fold predictions are inconsistent with the provided label."
                ),
                evidence={
                    "provided_label": int(labels[index]),
                    "suggested_label": suggested,
                    "provided_probability": quality,
                    "suggested_probability": float(probabilities[index, suggested]),
                    "fold": int(fold_ids[index]),
                },
                method=MethodIdentity("cleanlab_label_quality", "1"),
                recommended_disposition=generic_disposition(confidence),
            )
        )
    return findings, affected


def _outlier_findings(
    manifest: DatasetManifest, embeddings: np.ndarray, config: DataIntegrityConfig
) -> tuple[list[Finding], set[int]]:
    from sklearn.ensemble import IsolationForest

    detector = IsolationForest(
        contamination=config.isolation_contamination, random_state=config.seed
    )
    detector.fit(embeddings)
    scores = -detector.score_samples(embeddings)
    threshold = float(np.quantile(scores, config.outlier_percentile))
    findings: list[Finding] = []
    affected: set[int] = set()
    for index, score in enumerate(scores):
        confidence = empirical_percentile(float(score), scores)
        if confidence < config.outlier_percentile:
            continue
        affected.add(index)
        findings.append(
            Finding(
                finding_type=FindingType.STATISTICAL_OUTLIER,
                pillar=Pillar.F1,
                affected_asset=AssetLocator(
                    "sample",
                    manifest.samples[index].sample_id,
                    source_id=manifest.samples[index].source_id,
                ),
                severity=Severity.HIGH if confidence >= 0.95 else Severity.MEDIUM,
                raw_score=float(score),
                decision_threshold=threshold,
                confidence=confidence,
                confidence_normalizer="empirical_percentile_v1",
                human_readable_reason=(
                    "Embedding is in the configured upper tail of Isolation Forest adverse scores."
                ),
                evidence={"percentile": confidence},
                method=MethodIdentity("isolation_forest", "1"),
                recommended_disposition=generic_disposition(confidence),
            )
        )
    return findings, affected


def _source_assessments(
    manifest: DatasetManifest, affected: set[int], config: DataIntegrityConfig
) -> tuple[list[dict[str, Any]], list[Finding], bool]:
    from scipy.stats import chi2_contingency

    source_indices: dict[str, list[int]] = defaultdict(list)
    for index, sample in enumerate(manifest.samples):
        source_indices[sample.source_id].append(index)
    total_rate = len(affected) / len(manifest.samples)
    rows = [
        [
            sum(index in affected for index in indices),
            sum(index not in affected for index in indices),
        ]
        for indices in source_indices.values()
    ]
    p_value: float | None = None
    available = False
    if len(affected) >= config.source_min_anomalies and len(rows) >= 2:
        try:
            _, candidate_p, _, expected = chi2_contingency(rows)
            if np.all(expected >= 5):
                p_value, available = float(candidate_p), True
        except ValueError:
            pass
    assessments: list[dict[str, Any]] = []
    findings: list[Finding] = []
    for source_id, indices in sorted(source_indices.items()):
        anomalies = sum(index in affected for index in indices)
        rate = anomalies / len(indices)
        multiplier = rate / total_rate if total_rate > 0 else None
        if anomalies == 0:
            disposition = Disposition.ACCEPT
        elif (
            available
            and p_value is not None
            and p_value < config.source_p_value
            and multiplier is not None
            and multiplier > config.source_rate_multiplier
        ):
            disposition = Disposition.QUARANTINE
        else:
            disposition = Disposition.REVIEW
        assessments.append(
            {
                "source_id": source_id,
                "sample_count": len(indices),
                "anomaly_count": anomalies,
                "anomaly_rate": rate,
                "concentration_status": "completed" if available else "unavailable",
                "p_value": p_value,
                "dataset_rate_multiplier": multiplier,
                "disposition": disposition.value,
            }
        )
        if anomalies:
            findings.append(
                Finding(
                    finding_type=FindingType.SOURCE_CONCENTRATION,
                    pillar=Pillar.F1,
                    affected_asset=AssetLocator("source", source_id, source_id=source_id),
                    severity=Severity.HIGH
                    if disposition is Disposition.QUARANTINE
                    else Severity.MEDIUM,
                    raw_score=multiplier,
                    decision_threshold=(
                        f"p<{config.source_p_value} and " f"rate>{config.source_rate_multiplier}x"
                    ),
                    confidence=0.95 if disposition is Disposition.QUARANTINE else 0.70,
                    confidence_normalizer="source_rule_v1",
                    human_readable_reason=(
                        "Source contains anomalous samples; concentration policy was applied."
                    ),
                    evidence=assessments[-1],
                    method=MethodIdentity("source_concentration", "1"),
                    recommended_disposition=disposition,
                )
            )
    return assessments, findings, available


@dataclass(frozen=True)
class DataIntegrityResult:
    assessment: ModuleAssessment
    source_assessments: tuple[dict[str, Any], ...]


class DataIntegrityModule:
    def __init__(self, config: DataIntegrityConfig | None = None) -> None:
        self.config = config or DataIntegrityConfig()

    def analyze(self, manifest: DatasetManifest, embeddings: np.ndarray) -> DataIntegrityResult:
        matrix = np.asarray(embeddings, dtype=np.float64)
        if (
            matrix.ndim != 2
            or matrix.shape[0] != len(manifest.samples)
            or not np.all(np.isfinite(matrix))
        ):
            raise ValueError(
                "embeddings must be finite [sample, feature] values matching the manifest"
            )
        findings: list[Finding] = []
        affected: set[int] = set()
        executed: list[str] = []
        unavailable: list[UnavailableMethod] = []
        for name, operation in (
            ("cleanlab_label_quality", lambda: _label_findings(manifest, matrix, self.config)),
            ("phash_cosine_duplicates", lambda: _duplicate_findings(manifest, matrix, self.config)),
            ("isolation_forest", lambda: _outlier_findings(manifest, matrix, self.config)),
        ):
            try:
                method_findings, method_affected = operation()
                findings.extend(method_findings)
                affected.update(method_affected)
                executed.append(name)
            except (ImportError, RuntimeError, ValueError) as exc:
                unavailable.append(UnavailableMethod(name, str(exc)))
        try:
            sources, source_findings, _ = _source_assessments(manifest, affected, self.config)
            findings.extend(source_findings)
            executed.append("source_concentration")
        except (ImportError, RuntimeError, ValueError) as exc:
            sources = []
            unavailable.append(UnavailableMethod("source_concentration", str(exc)))
        status = (
            ModuleStatus.COMPLETED
            if not unavailable
            else (ModuleStatus.PARTIAL if executed else ModuleStatus.UNAVAILABLE)
        )
        return DataIntegrityResult(
            ModuleAssessment(status, tuple(findings), tuple(executed), tuple(unavailable)),
            tuple(sources),
        )
