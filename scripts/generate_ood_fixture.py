"""Generate deterministic RGB noise images for an explicitly synthetic OOD smoke fixture."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    if args.count < 1:
        parser.error("count must be positive")
    images = args.output_dir / "images"
    images.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(args.seed)
    rows = []
    for index in range(args.count):
        name = f"noise_{index:05d}.png"
        Image.fromarray(rng.integers(0, 256, (32, 32, 3), dtype=np.uint8)).save(images / name)
        rows.append(
            {
                "sample_id": f"ood-{index}",
                "image_path": name,
                "label": 0,
                "source_id": "synthetic-noise",
            }
        )
    manifest = {
        "dataset_id": f"synthetic-ood-seed-{args.seed}",
        "samples": rows,
        "fixture_limitation": (
            "Synthetic noise is a smoke fixture, not the normative SVHN benchmark."
        ),
    }
    (args.output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
