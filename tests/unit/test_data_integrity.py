from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from sentinel.adapters.datasets import DatasetManifest
from sentinel.core.models import DatasetSample
from sentinel.modules.data_integrity import (
    DataIntegrityConfig,
    DataIntegrityModule,
    _cosine_pairs,
    _phash_pairs,
)


class DataIntegrityTests(unittest.TestCase):
    def test_chunked_cosine_emits_canonical_pairs(self) -> None:
        embeddings = np.array([[1, 0], [1, 0], [0, 1]], dtype=np.float64)
        pairs = _cosine_pairs(embeddings, threshold=0.95, k=2, chunk_size=1)
        self.assertEqual(set(pairs), {(0, 1)})
        self.assertAlmostEqual(pairs[(0, 1)]["cosine_similarity"], 1.0)

    def test_phash_primary_detector_finds_exact_duplicate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, second = root / "a.png", root / "b.png"
            pixels = np.arange(16 * 16 * 3, dtype=np.uint8).reshape(16, 16, 3)
            Image.fromarray(pixels).save(first)
            Image.fromarray(pixels).save(second)
            manifest = DatasetManifest(
                "fixture", root, (DatasetSample("a", first, 0), DatasetSample("b", second, 0)), 2
            )
            pairs = _phash_pairs(manifest, radius=8)
            self.assertEqual(pairs[(0, 1)]["phash_distance"], 0)

    def test_complete_module_executes_all_four_methods(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rng = np.random.default_rng(42)
            samples = []
            for index in range(20):
                path = root / f"{index}.png"
                Image.fromarray(rng.integers(0, 256, (16, 16, 3), dtype=np.uint8)).save(path)
                samples.append(
                    DatasetSample(f"s{index}", path, index % 2, source_id=f"src{index % 2}")
                )
            manifest = DatasetManifest("fixture", root, tuple(samples), 2)
            embeddings = rng.normal(size=(20, 8)).astype(np.float32)
            result = DataIntegrityModule(DataIntegrityConfig(neighbor_chunk_size=7)).analyze(
                manifest, embeddings
            )
            self.assertIn(result.assessment.status.value, ("completed", "partial"))
            self.assertEqual(
                set(result.assessment.methods_executed),
                {
                    "cleanlab_label_quality",
                    "phash_cosine_duplicates",
                    "isolation_forest",
                    "source_concentration",
                },
            )
            self.assertEqual(len(result.source_assessments), 2)

    def test_full_analysis_degrades_label_check_when_fold_counts_are_insufficient(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            samples = []
            for index in range(4):
                path = root / f"{index}.png"
                Image.new("RGB", (16, 16), (index * 20, 0, 0)).save(path)
                samples.append(DatasetSample(str(index), path, index % 2, f"source-{index % 2}"))
            manifest = DatasetManifest("fixture", root, tuple(samples), 2)
            embeddings = np.eye(4, dtype=np.float64)
            result = DataIntegrityModule(
                DataIntegrityConfig(cosine_neighbors=2, neighbor_chunk_size=2)
            ).analyze(manifest, embeddings)
            unavailable = {item.method for item in result.assessment.methods_unavailable}
            self.assertIn("cleanlab_label_quality", unavailable)
            self.assertIn(result.assessment.status.value, {"partial", "unavailable"})


if __name__ == "__main__":
    unittest.main()
