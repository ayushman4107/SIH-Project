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
    parser.add_argument("--data-root", type=Path, default=Path("reference_data"))
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--ood-dataset", choices=["svhn", "cifar100", "noise"], default="svhn")
    args = parser.parse_args()
    if args.count < 1:
        parser.error("count must be positive")
    images = args.output_dir / "images"
    images.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(args.seed)
    rows = []

    if args.ood_dataset == "noise":
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
        manifest_desc = "Synthetic noise is a smoke fixture, not the normative benchmark."
    else:
        try:
            from torchvision import datasets
        except ImportError as exc:
            raise RuntimeError("torchvision required to generate real OOD fixtures") from exc

        args.data_root.mkdir(parents=True, exist_ok=True)
        if args.ood_dataset == "svhn":
            dataset = datasets.SVHN(args.data_root, split="test", download=False)
        else:
            dataset = datasets.CIFAR100(args.data_root, train=False, download=False)

        indices = rng.choice(len(dataset), size=min(args.count, len(dataset)), replace=False)
        for i, idx in enumerate(indices):
            image, label = dataset[idx]
            name = f"{args.ood_dataset}_{i:05d}.png"
            image.save(images / name)
            rows.append(
                {
                    "sample_id": f"ood-{args.ood_dataset}-{i}",
                    "image_path": name,
                    "label": int(label),
                    "source_id": f"torchvision-{args.ood_dataset}",
                }
            )
        manifest_desc = f"{args.ood_dataset} benchmark dataset."

    manifest = {
        "dataset_id": f"{args.ood_dataset}-ood-seed-{args.seed}",
        "samples": rows,
        "fixture_limitation": manifest_desc,
    }
    (args.output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
