from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from scripts.generate_synthetic_models import (
    apply_checkerboard,
    evaluate_quality_gate,
    select_poison_indices,
)
from sentinel.core.enums import Disposition, FindingType, Pillar, Severity
from sentinel.core.errors import ConfigurationError, ValidationError
from sentinel.core.models import AssetLocator, Finding, MethodIdentity
from sentinel.core.schema_registry import SchemaRegistry
from sentinel.utils.config import load_config


class ContractTests(unittest.TestCase):
    def test_all_schemas_are_offline_json_documents(self) -> None:
        registry = SchemaRegistry()
        self.assertEqual(len(registry._schemas), 6)
        for schema in registry._schemas.values():
            self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
            self.assertTrue(schema["$id"].startswith("https://sentinel.local/"))

    def test_finding_serialization_uses_wire_values(self) -> None:
        finding = Finding(
            finding_type=FindingType.LABEL_ERROR,
            pillar=Pillar.F1,
            affected_asset=AssetLocator("sample", "s1"),
            severity=Severity.MEDIUM,
            raw_score=0.1,
            decision_threshold=0.7,
            confidence=0.9,
            confidence_normalizer="cleanlab_inverse_quality_v1",
            human_readable_reason="fixture",
            evidence={},
            method=MethodIdentity("cleanlab_label_quality", "1"),
            recommended_disposition=Disposition.REVIEW,
        )
        payload = finding.to_dict()
        self.assertEqual(payload["finding_type"], "label_error")
        self.assertEqual(payload["recommended_disposition"], "review")
        self.assertEqual(payload["calibration_status"], "uncalibrated")

    def test_schema_accepts_valid_and_rejects_invalid_fixture_when_available(self) -> None:
        registry = SchemaRegistry()
        fixtures = Path(__file__).resolve().parents[1] / "fixtures"
        valid = json.loads((fixtures / "valid_finding.json").read_text(encoding="utf-8"))
        invalid = json.loads((fixtures / "invalid_finding.json").read_text(encoding="utf-8"))
        try:
            registry.validate("finding", valid)
        except ValidationError as exc:
            if "jsonschema is required" in str(exc):
                self.skipTest(str(exc))
            raise
        with self.assertRaises(ValidationError):
            registry.validate("finding", invalid)


class ConfigurationTests(unittest.TestCase):
    def test_json_config_materializes_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps({"seed": 9}), encoding="utf-8")
            config = load_config(path)
        self.assertEqual(config["seed"], 9)
        self.assertEqual(config["detectors"]["phash_hamming_threshold"], 8)

    def test_unknown_top_level_key_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps({"surprise": True}), encoding="utf-8")
            with self.assertRaises(ConfigurationError):
                load_config(path)


class BenchmarkContractTests(unittest.TestCase):
    def test_checkerboard_exact_for_chw_and_hwc(self) -> None:
        chw = apply_checkerboard(np.zeros((3, 8, 8), dtype=np.float32))
        hwc = apply_checkerboard(np.zeros((8, 8, 3), dtype=np.uint8))
        expected = np.array([[1, 0, 1], [0, 1, 0], [1, 0, 1]], dtype=np.float32)
        np.testing.assert_array_equal(chw[0, -3:, -3:], expected)
        np.testing.assert_array_equal(hwc[-3:, -3:, 2], expected * 255)

    def test_poison_indices_are_deterministic_and_non_target(self) -> None:
        labels = np.tile(np.arange(10), 20)
        first = select_poison_indices(labels, seed=42)
        second = select_poison_indices(labels, seed=42)
        np.testing.assert_array_equal(first, second)
        self.assertTrue(np.all(labels[first] != 0))
        self.assertEqual(len(first), 18)

    def test_quality_gate_semantics(self) -> None:
        self.assertTrue(evaluate_quality_gate("clean", 0.75, 0.20).accepted)
        self.assertTrue(evaluate_quality_gate("poisoned", 0.75, 0.80).accepted)
        self.assertFalse(evaluate_quality_gate("poisoned", 0.74, 0.99).accepted)


if __name__ == "__main__":
    unittest.main()
