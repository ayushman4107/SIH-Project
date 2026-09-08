from __future__ import annotations

import unittest

import numpy as np

from sentinel.modules.distribution_shift import (
    DistributionShiftModule,
    predictive_entropy,
    stable_softmax,
)


class DistributionShiftTests(unittest.TestCase):
    def setUp(self) -> None:
        rng = np.random.default_rng(42)
        self.reference = rng.normal(size=(100, 8))
        self.incoming = rng.normal(size=(12, 8))

    def test_softmax_is_stable_float32(self) -> None:
        probabilities = stable_softmax(np.array([[1000, 1001, 999]], dtype=np.float32))
        self.assertEqual(probabilities.dtype, np.dtype("float32"))
        self.assertAlmostEqual(float(probabilities.sum()), 1.0, places=6)
        self.assertTrue(np.all(np.isfinite(predictive_entropy([[1000, 1001, 999]]))))

    def test_high_entropy_ratio_is_fixed_review_and_dependency_is_declared(self) -> None:
        reference_logits = np.tile([12.0, -12.0], (100, 1))
        incoming_logits = np.zeros((12, 2), dtype=np.float32)
        result = DistributionShiftModule().analyze(
            reference_embeddings=self.reference,
            incoming_embeddings=self.incoming,
            reference_logits=reference_logits,
            incoming_logits=incoming_logits,
            model_suspicious=True,
        )
        drift = [
            item
            for item in result.assessment.findings
            if item.finding_type.value == "possible_drift"
        ]
        self.assertEqual(drift[0].recommended_disposition.value, "review")
        self.assertEqual(result.model_dependency, "depends_on_suspicious_model")

    def test_low_and_neutral_entropy_characterizations(self) -> None:
        uniform_reference = np.zeros((100, 2), dtype=np.float32)
        confident_incoming = np.tile([12.0, -12.0], (12, 1))
        low = DistributionShiftModule().analyze(
            reference_embeddings=self.reference,
            incoming_embeddings=self.incoming,
            reference_logits=uniform_reference,
            incoming_logits=confident_incoming,
        )
        self.assertEqual(low.characterization, "suspicious")

        rng = np.random.default_rng(7)
        ref_logits = rng.normal(size=(100, 3)).astype(np.float32)
        in_logits = rng.normal(size=(12, 3)).astype(np.float32)
        neutral = DistributionShiftModule().analyze(
            reference_embeddings=self.reference,
            incoming_embeddings=self.incoming,
            reference_logits=ref_logits,
            incoming_logits=in_logits,
        )
        self.assertEqual(neutral.characterization, "inconclusive")


if __name__ == "__main__":
    unittest.main()
