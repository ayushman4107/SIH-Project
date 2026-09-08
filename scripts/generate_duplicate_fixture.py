"""Build a deterministic near-duplicate image fixture from a classification manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageEnhance


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--count", type=int, default=20)
    args = parser.parse_args()
    payload = json.loads(args.manifest.read_text(encoding="utf-8"))
    source_rows = payload["samples"] if isinstance(payload, dict) else payload
    selected = source_rows[: args.count]
    images = args.output_dir / "images"
    images.mkdir(parents=True, exist_ok=True)
    rows = []
    for index, row in enumerate(selected):
        source = args.dataset_root / row["image_path"]
        with Image.open(source) as image:
            rgb = image.convert("RGB")
            original_name = f"pair_{index:04d}_original.png"
            variant_name = f"pair_{index:04d}_variant.jpg"
            rgb.save(images / original_name)
            resized = rgb.resize((max(4, rgb.width - 1), max(4, rgb.height - 1))).resize(rgb.size)
            ImageEnhance.Brightness(resized).enhance(0.98).save(
                images / variant_name, format="JPEG", quality=92
            )
        base = {
            "label": int(row["label"]),
            "source_id": str(row.get("source_id") or "unknown"),
        }
        rows.append({"sample_id": f"pair-{index}-original", "image_path": original_name, **base})
        rows.append({"sample_id": f"pair-{index}-variant", "image_path": variant_name, **base})
    manifest = {
        "dataset_id": "seeded-near-duplicate-fixture",
        "samples": rows,
        "expected_pairs": args.count,
    }
    (args.output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
