"""Generate deterministic CIFAR-10 BadNets benchmark models.

Training is implemented in a later workstream. This foundation module freezes the exact
poisoning transform, sample selection, and quality-gate semantics before long jobs begin.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np


TARGET_CLASS = 0
INITIAL_SEEDS = (42, 43, 44, 45, 46)
CHECKERBOARD = np.array(
    [[1.0, 0.0, 1.0], [0.0, 1.0, 0.0], [1.0, 0.0, 1.0]], dtype=np.float32
)


def apply_checkerboard(image: np.ndarray) -> np.ndarray:
    """Return a copy with the exact RGB 3x3 bottom-right checkerboard applied.

    Accepted layouts are CHW or HWC with three channels. Floating images use 0/1 and
    integer images use 0/the dtype maximum.
    """
    array = np.asarray(image)
    if array.ndim != 3:
        raise ValueError("image must be a three-dimensional CHW or HWC array")
    channel_first = array.shape[0] == 3
    channel_last = array.shape[-1] == 3
    if not channel_first and not channel_last:
        raise ValueError("image must contain exactly three channels")
    result = array.copy()
    high = 1.0 if np.issubdtype(result.dtype, np.floating) else np.iinfo(result.dtype).max
    patch = (CHECKERBOARD * high).astype(result.dtype, copy=False)
    if channel_first:
        result[:, -3:, -3:] = np.broadcast_to(patch, (3, 3, 3))
    else:
        result[-3:, -3:, :] = np.repeat(patch[:, :, None], 3, axis=2)
    return result


def select_poison_indices(
    labels: np.ndarray, seed: int, poisoning_rate: float = 0.10, target_class: int = TARGET_CLASS
) -> np.ndarray:
    """Select exactly floor(rate * non-target count) deterministic non-target indices."""
    if not 0.0 <= poisoning_rate <= 1.0:
        raise ValueError("poisoning_rate must be within [0, 1]")
    candidates = np.flatnonzero(np.asarray(labels) != target_class)
    count = int(len(candidates) * poisoning_rate)
    rng = np.random.default_rng(seed)
    return np.sort(rng.choice(candidates, size=count, replace=False))


@dataclass(frozen=True)
class QualityGate:
    model_kind: str
    clean_test_accuracy: float
    triggered_target_rate: float
    accepted: bool
    reason: str | None


def evaluate_quality_gate(
    model_kind: str, clean_test_accuracy: float, triggered_target_rate: float
) -> QualityGate:
    if model_kind not in {"clean", "poisoned"}:
        raise ValueError("model_kind must be clean or poisoned")
    rate_limit = 0.20 if model_kind == "clean" else 0.80
    accuracy_ok = clean_test_accuracy >= 0.75
    rate_ok = triggered_target_rate <= rate_limit if model_kind == "clean" else triggered_target_rate >= rate_limit
    accepted = accuracy_ok and rate_ok
    reasons = []
    if not accuracy_ok:
        reasons.append("clean_test_accuracy_below_0.75")
    if not rate_ok:
        reasons.append("triggered_rate_gate_failed")
    return QualityGate(model_kind, clean_test_accuracy, triggered_target_rate, accepted, ";".join(reasons) or None)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("artifacts/benchmark_plan.json"))
    parser.add_argument("--dry-run", action="store_true", help="emit the frozen benchmark plan")
    args = parser.parse_args()
    if not args.dry_run:
        parser.error("training is enabled by the F2 implementation phase; use --dry-run for now")
    plan = {
        "architectures": {"resnet18": {"clean": 5, "poisoned": 5}, "vgg16": {"clean": 1, "poisoned": 1}},
        "initial_seeds": list(INITIAL_SEEDS),
        "target_class": TARGET_CLASS,
        "poisoning_rate": 0.10,
        "trigger": CHECKERBOARD.tolist(),
        "clean_gate": {"clean_test_accuracy": 0.75, "max_triggered_target_rate": 0.20},
        "poison_gate": {"clean_test_accuracy": 0.75, "min_asr": 0.80},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
