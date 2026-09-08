"""Create a deterministic label-flip manifest while preserving source occurrences."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def inject_flips(
    payload: dict, fraction: float, num_classes: int, seed: int
) -> tuple[dict, list[str]]:
    if not 0 < fraction < 1:
        raise ValueError("fraction must be within (0, 1)")
    rows = [dict(row) for row in payload["samples"]]
    count = int(len(rows) * fraction)
    rng = np.random.default_rng(seed)
    indices = np.sort(rng.choice(len(rows), size=count, replace=False))
    changed = []
    for index in indices:
        original = int(rows[index]["label"])
        offset = int(rng.integers(1, num_classes))
        rows[index]["label"] = (original + offset) % num_classes
        changed.append(str(rows[index]["sample_id"]))
    result = dict(payload)
    result["samples"] = rows
    result["fixture"] = {
        "type": "label_flips",
        "fraction": fraction,
        "seed": seed,
        "changed_sample_ids": changed,
    }
    return result, changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fraction", type=float, required=True)
    parser.add_argument("--num-classes", type=int, default=10)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    result, _ = inject_flips(payload, args.fraction, args.num_classes, args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
