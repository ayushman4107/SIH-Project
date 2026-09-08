import os
import unittest
from unittest.mock import MagicMock

from scripts.generate_synthetic_models import _seed_everything


class TestDeterminism(unittest.TestCase):
    def test_seed_everything_sets_determinism(self):
        torch_mock = MagicMock()
        torch_mock.cuda.is_available.return_value = True

        # Clear env to ensure we test setting it
        if "CUBLAS_WORKSPACE_CONFIG" in os.environ:
            del os.environ["CUBLAS_WORKSPACE_CONFIG"]

        _seed_everything(42, torch_mock)

        self.assertEqual(os.environ.get("CUBLAS_WORKSPACE_CONFIG"), ":4096:8")
        self.assertFalse(torch_mock.backends.cudnn.benchmark)
        self.assertTrue(torch_mock.backends.cudnn.deterministic)
        torch_mock.use_deterministic_algorithms.assert_called_with(True, warn_only=False)
        torch_mock.cuda.manual_seed_all.assert_called_with(42)


if __name__ == "__main__":
    unittest.main()
