from __future__ import annotations

import unittest
from pathlib import Path

from sentinel.adapters.models import load_model
from sentinel.core.errors import CapabilityDeferredError, ValidationError


class ModelAdapterTests(unittest.TestCase):
    def test_onnx_is_explicitly_deferred_without_importing_runtime(self) -> None:
        with self.assertRaises(CapabilityDeferredError):
            load_model(Path("candidate.onnx"), "onnx", "resnet18", 10)

    def test_unknown_format_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            load_model(Path("candidate.bin"), "unknown", "resnet18", 10)


if __name__ == "__main__":
    unittest.main()
