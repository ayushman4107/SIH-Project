from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from sentinel.adapters.datasets import load_classification_manifest
from sentinel.core.errors import ValidationError


class DatasetAdapterTests(unittest.TestCase):
    def _fixture(self, directory: str, rows: list[dict]) -> tuple[Path, Path]:
        root = Path(directory) / "images"
        root.mkdir()
        Image.new("RGB", (8, 8), (1, 2, 3)).save(root / "one.png")
        manifest = Path(directory) / "manifest.json"
        manifest.write_text(json.dumps({"dataset_id": "fixture", "samples": rows}), encoding="utf-8")
        return manifest, root

    def test_manifest_preserves_occurrences_and_normalizes_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            rows = [{"sample_id": "s1", "image_path": "one.png", "label": 2}]
            manifest_path, root = self._fixture(directory, rows)
            manifest = load_classification_manifest(manifest_path, root, 10)
            self.assertEqual(manifest.dataset_id, "fixture")
            self.assertEqual(manifest.samples[0].source_id, "unknown")

    def test_duplicate_ids_and_path_escape_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            duplicate = [
                {"sample_id": "s1", "image_path": "one.png", "label": 1},
                {"sample_id": "s1", "image_path": "one.png", "label": 1},
            ]
            manifest_path, root = self._fixture(directory, duplicate)
            with self.assertRaises(ValidationError):
                load_classification_manifest(manifest_path, root, 10)

        with tempfile.TemporaryDirectory() as directory:
            outside = Path(directory) / "outside.png"
            Image.new("RGB", (2, 2)).save(outside)
            rows = [{"sample_id": "s1", "image_path": "../outside.png", "label": 1}]
            manifest_path, root = self._fixture(directory, rows)
            with self.assertRaises(ValidationError):
                load_classification_manifest(manifest_path, root, 10)


if __name__ == "__main__":
    unittest.main()
