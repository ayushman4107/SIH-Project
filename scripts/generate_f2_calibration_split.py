"""Generate cryptographically separate calibration and evaluation splits for F2."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("reference_data"))
    parser.add_argument("--output-dir", type=Path, default=Path("reference_data/cifar10_f2_split"))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--calib-size", type=int, default=2000)
    args = parser.parse_args()

    try:
        from torchvision import datasets
    except ImportError as exc:
        raise RuntimeError("torchvision required to generate splits") from exc

    args.output_dir.mkdir(parents=True, exist_ok=True)
    images_dir = args.output_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    dataset = datasets.CIFAR10(args.data_root, train=False, download=False)
    total_size = len(dataset)
    if args.calib_size >= total_size:
        raise ValueError("calib_size must be strictly less than total dataset size")

    rng = np.random.default_rng(args.seed)
    indices = np.arange(total_size)
    rng.shuffle(indices)

    calib_indices = indices[:args.calib_size]
    eval_indices = indices[args.calib_size:]

    def export_split(split_name: str, split_indices: np.ndarray) -> str:
        rows = []
        for i in split_indices:
            image, label = dataset[int(i)]
            name = f"cifar10_test_{i:05d}.png"
            img_path = images_dir / name
            if not img_path.exists():
                image.save(img_path)
            rows.append(
                {
                    "sample_id": f"cifar10-test-{i}",
                    "image_path": f"images/{name}",
                    "label": int(label),
                    "source_id": "torchvision-cifar10-test",
                }
            )
        manifest = {
            "dataset_id": f"cifar10-{split_name}-seed-{args.seed}",
            "samples": rows,
            "split_size": len(split_indices),
        }
        manifest_path = args.output_dir / f"{split_name}_manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        import hashlib
        return hashlib.sha256(manifest_path.read_bytes()).hexdigest()

    calib_hash = export_split("calib", calib_indices)
    eval_hash = export_split("eval", eval_indices)

    print(f"Calibration split generated. Hash: {calib_hash}")
    print(f"Evaluation split generated. Hash: {eval_hash}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
