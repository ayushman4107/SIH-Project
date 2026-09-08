"""Generate a physical poisoned dataset on disk for F1 Sybil / Data Integrity testing."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("reference_data"))
    parser.add_argument("--output-dir", type=Path, default=Path("reference_data/cifar10_f1_poisoned"))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--num-vendors", type=int, default=5)
    parser.add_argument("--poisoning-rate", type=float, default=0.05)
    parser.add_argument("--target-class", type=int, default=0)
    args = parser.parse_args()

    try:
        from torchvision import datasets
    except ImportError as exc:
        raise RuntimeError("torchvision required to generate splits") from exc

    args.output_dir.mkdir(parents=True, exist_ok=True)
    images_dir = args.output_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    full_train_base = datasets.CIFAR10(args.data_root, train=True, download=False)
    
    # Mirror the exact same deterministic split used in generate_synthetic_models.py
    split_rng = np.random.default_rng(42)
    indices = split_rng.permutation(len(full_train_base))
    train_indices = indices[:-5000]
    
    # We will export the 45000-image train split
    rng = np.random.default_rng(args.seed)
    
    # Select exactly 5% of the total dataset for in-place poisoning
    total_images = len(train_indices)
    poison_count = int(total_images * args.poisoning_rate)
    
    # We select 5% uniformly across all images, disregarding original class
    poison_indices_in_subset = np.sort(rng.choice(total_images, size=poison_count, replace=False))
    poison_set = set(poison_indices_in_subset.tolist())

    # Build the checkerboard trigger
    CHECKERBOARD = np.array([[1.0, 0.0, 1.0], [0.0, 1.0, 0.0], [1.0, 0.0, 1.0]], dtype=np.float32)
    
    def apply_trigger(image_array: np.ndarray) -> np.ndarray:
        # image_array is HWC uint8
        result = image_array.copy()
        patch = (CHECKERBOARD * 255.0).astype(np.uint8)
        result[-3:, -3:, :] = np.repeat(patch[:, :, None], 3, axis=2)
        return result

    rows = []
    
    # Sybil partition setup: randomly assign each of the 45000 images to a vendor
    vendor_assignments = rng.integers(0, args.num_vendors, size=len(train_indices))
    
    from PIL import Image

    for i, idx in enumerate(train_indices):
        img_pil, label = full_train_base[int(idx)]
        vendor_id = f"vendor_{vendor_assignments[i]}"
        
        is_poison = i in poison_set
        out_label = args.target_class if is_poison else label
        
        if is_poison:
            img_arr = np.array(img_pil)
            img_arr = apply_trigger(img_arr)
            img_pil = Image.fromarray(img_arr)
            
        name = f"f1_train_{i:05d}.png"
        img_path = images_dir / name
        img_pil.save(img_path)
        
        rows.append({
            "sample_id": f"f1-train-{i}",
            "image_path": f"images/{name}",
            "label": int(out_label),
            "source_id": vendor_id
        })

    manifest = {
        "dataset_id": f"cifar10-f1-poisoned-seed-{args.seed}",
        "samples": rows,
        "poison_count": poison_count
    }
    
    manifest_path = args.output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    
    print(f"F1 Sybil Poisoned Dataset generated at {args.output_dir} with {poison_count} triggers distributed across {args.num_vendors} vendors. Total size: {len(rows)}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
