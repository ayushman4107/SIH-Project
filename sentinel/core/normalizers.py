"""Deterministic adverse-finding confidence normalizers."""

from __future__ import annotations

import math
from collections.abc import Sequence

from sentinel.core.enums import Disposition


def clamp(value: float) -> float:
    if not math.isfinite(value):
        raise ValueError("confidence inputs must be finite")
    return min(max(float(value), 0.0), 1.0)


def label_quality_confidence(quality: float) -> float:
    return clamp(1.0 - quality)


def phash_confidence(distance: int) -> float:
    if not 0 <= distance <= 8:
        raise ValueError("pHash finding distance must be in [0, 8]")
    return clamp(0.70 + 0.30 * (8 - distance) / 8)


def cosine_confidence(similarity: float) -> float:
    if similarity < 0.95:
        raise ValueError("cosine finding similarity must be at least 0.95")
    return clamp(0.70 + 0.30 * (similarity - 0.95) / 0.05)


def empirical_percentile(value: float, reference: Sequence[float]) -> float:
    finite = [float(item) for item in reference if math.isfinite(float(item))]
    if not finite:
        raise ValueError("at least one finite reference score is required")
    return clamp(sum(item <= value for item in finite) / len(finite))


def threshold_excess_confidence(value: float, threshold: float, epsilon: float = 1e-12) -> float:
    if value <= threshold:
        raise ValueError("threshold-excess confidence applies only above threshold")
    excess_ratio = (value - threshold) / max(threshold, epsilon)
    return clamp(0.70 + 0.30 * min(excess_ratio, 1.0))


def low_entropy_confidence(ratio: float) -> float:
    if ratio > 0.7:
        raise ValueError("low-entropy confidence applies only at or below 0.7")
    return clamp(0.70 + 0.30 * (0.7 - ratio) / 0.7)


def generic_disposition(confidence: float) -> Disposition:
    value = clamp(confidence)
    if value >= 0.95:
        return Disposition.QUARANTINE
    if value >= 0.70:
        return Disposition.REVIEW
    return Disposition.ACCEPT
