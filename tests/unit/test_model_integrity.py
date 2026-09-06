from __future__ import annotations

import unittest

import numpy as np

from sentinel.modules.model_integrity import (
    ModelIntegrityModule,
    analyzed_matrices,
    normalized_spectra,
)


def _state(seed: int, *, anomalous: bool = False) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(seed)
    conv = rng.normal(size=(8, 3, 3, 3))
    linear = rng.normal(size=(10, 8))
    if anomalous:
        conv[:] = 0
        conv[:, 0, 0, 0] = np.linspace(1, 20, 8)
        linear[:] = 0
        linear[:, 0] = np.linspace(1, 40, 10)
    return {
        "layer1.weight": conv,
        "head.weight": linear,
        "head.bias": rng.normal(size=10),
        "norm.weight": rng.normal(size=8),
    }


class ModelIntegrityTests(unittest.TestCase):
    def test_tensor_shaping_and_exclusions(self) -> None:
        matrices = analyzed_matrices(_state(1))
        self.assertEqual(matrices["layer1.weight"].shape, (8, 27))
        self.assertEqual(matrices["head.weight"].shape, (10, 8))
        self.assertNotIn("head.bias", matrices)
        self.assertNotIn("norm.weight", matrices)
        for spectrum in normalized_spectra(_state(1)).values():
            self.assertAlmostEqual(float(spectrum.sum()), 1.0)

    def test_nextafter_threshold_never_flags_calibration_copy(self) -> None:
        references = [_state(seed) for seed in range(5)]
        result = ModelIntegrityModule().analyze(
            candidate_state=references[0],
            reference_states=references,
            architecture_id="resnet18",
            candidate_id="clean-copy",
        )
        self.assertIn(result.assessment.status.value, ("completed", "partial"))
        self.assertEqual(result.assessment.findings, ())
        self.assertGreater(result.threshold, max(result.calibration_scores))

    def test_rank_collapsed_candidate_is_flagged(self) -> None:
        references = [_state(seed) for seed in range(5)]
        result = ModelIntegrityModule().analyze(
            candidate_state=_state(99, anomalous=True),
            reference_states=references,
            architecture_id="resnet18",
            candidate_id="poisoned",
        )
        self.assertIn(result.assessment.status.value, ("completed", "partial"))
        self.assertEqual(len(result.assessment.findings), 1)
        self.assertEqual(
            result.assessment.findings[0].finding_type.value, "weight_spectral_anomaly"
        )

    def test_shape_mismatch_is_unavailable_and_nonfinite_is_quarantined(self) -> None:
        references = [_state(seed) for seed in range(5)]
        mismatch = _state(6)
        mismatch["head.weight"] = np.ones((10, 9))
        result = ModelIntegrityModule().analyze(
            candidate_state=mismatch,
            reference_states=references,
            architecture_id="resnet18",
            candidate_id="bad-shape",
        )
        self.assertEqual(result.assessment.status.value, "unavailable")
        nonfinite = _state(7)
        nonfinite["head.weight"][0, 0] = np.nan
        result = ModelIntegrityModule().analyze(
            candidate_state=nonfinite,
            reference_states=references,
            architecture_id="resnet18",
            candidate_id="nan",
        )
        self.assertEqual(result.assessment.findings[0].recommended_disposition.value, "quarantine")

    def test_regularized_threshold_mode(self) -> None:
        references = [_state(seed) for seed in range(5)]
        nextafter_result = ModelIntegrityModule(threshold_mode="nextafter").analyze(
            candidate_state=_state(1),
            reference_states=references,
            architecture_id="resnet18",
            candidate_id="clean",
        )
        regularized_result = ModelIntegrityModule(threshold_mode="regularized", regularized_k=2.0).analyze(
            candidate_state=_state(1),
            reference_states=references,
            architecture_id="resnet18",
            candidate_id="clean",
        )
        self.assertGreaterEqual(regularized_result.threshold, nextafter_result.threshold)
        self.assertIn("mean", regularized_result.calibration_stats)
        self.assertIn("rule_of_three_upper_bound_fpr", regularized_result.calibration_stats)

    def test_eligible_tensor_criteria_and_margins(self) -> None:
        references = [_state(seed) for seed in range(5)]
        result = ModelIntegrityModule().analyze(
            candidate_state=_state(99, anomalous=True),
            reference_states=references,
            architecture_id="resnet18",
            candidate_id="poisoned",
        )
        self.assertIn("target_tensors", result.eligible_tensor_criteria)
        self.assertIn("poisoned", result.detection_margins)
        self.assertIsNotNone(result.threshold_margin_min)
        self.assertGreater(result.detection_margins["poisoned"], 0)
if __name__ == "__main__":
    unittest.main()
