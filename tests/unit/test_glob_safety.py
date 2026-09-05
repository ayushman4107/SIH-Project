import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

import yaml

from sentinel.pipeline import SentinelPipeline
from sentinel.utils.config import load_config


class TestGlobSafety(unittest.TestCase):
    def test_pipeline_ignores_subdirectories_for_references(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            
            # create config
            config_path = base / "config.yaml"
            config = {
                "references": {"model_directory": str(base / "refs")},
                "dataset_manifest": "dummy",
                "dataset_root": "dummy",
                "num_classes": 10,
                "resources": {"max_image_bytes": 100, "max_image_pixels": 100, "embedding_batch_size": 1, "neighbor_chunk_size": 1},
                "seed": 42,
                "detectors": {
                    "phash_hamming_threshold": 1,
                    "cosine_threshold": 0.9,
                    "cosine_neighbors": 1,
                    "outlier_percentile": 0.95,
                    "source_p_value": 0.05,
                    "source_rate_multiplier": 2.0,
                },
                "model": {"path": "dummy", "format": "pytorch", "architecture_id": "resnet18"},
                "extractor_weights": "dummy",
                "output_root": str(base / "out")
            }
            with open(config_path, "w") as f:
                yaml.dump(config, f)
            
            # create refs and a subfolder with a pt file
            refs_dir = base / "refs"
            refs_dir.mkdir()
            (refs_dir / "clean1.pt").write_text("dummy")
            sub_dir = refs_dir / "poisoned"
            sub_dir.mkdir()
            (sub_dir / "bad.pt").write_text("dummy")
            
            # We mock load_config and glob check
            # Instead of running the full pipeline, we'll just check iterdir behavior 
            # by looking at the patch that logs a warning
            
            with patch("sentinel.pipeline.load_config", return_value=config):
                with patch("logging.warning") as mock_warn:
                    with patch("sentinel.pipeline.load_classification_manifest") as mock_lcm:
                        mock_sample = MagicMock()
                        mock_sample.image_path = "dummy.png"
                        mock_lcm.return_value.samples = [mock_sample]
                        with patch("sentinel.pipeline.load_model"):
                            with patch("sentinel.pipeline.EmbeddingExtractor"):
                                try:
                                    SentinelPipeline().run(config_path)
                                except Exception as e:
                                    import traceback
                                    traceback.print_exc()
                                    pass
            
            mock_warn.assert_any_call(f"Reference directory {refs_dir} contains subdirectories. They will be ignored.")

if __name__ == "__main__":
    unittest.main()
