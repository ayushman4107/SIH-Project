from __future__ import annotations

import unittest

from sentinel.core.enums import Disposition
from sentinel.core.normalizers import (
    cosine_confidence,
    empirical_percentile,
    generic_disposition,
    label_quality_confidence,
    low_entropy_confidence,
    phash_confidence,
    threshold_excess_confidence,
)


class NormalizerTests(unittest.TestCase):
    def test_exact_boundaries(self) -> None:
        self.assertEqual(label_quality_confidence(0.1), 0.9)
        self.assertAlmostEqual(phash_confidence(8), 0.70)
        self.assertAlmostEqual(phash_confidence(0), 1.0)
        self.assertAlmostEqual(cosine_confidence(0.95), 0.70)
        self.assertAlmostEqual(cosine_confidence(1.0), 1.0)
        self.assertAlmostEqual(low_entropy_confidence(0.7), 0.70)
        self.assertAlmostEqual(threshold_excess_confidence(2.0, 1.0), 1.0)

    def test_empirical_percentile_and_disposition(self) -> None:
        self.assertEqual(empirical_percentile(2, [1, 2, 3, 4]), 0.5)
        self.assertIs(generic_disposition(0.69), Disposition.ACCEPT)
        self.assertIs(generic_disposition(0.70), Disposition.REVIEW)
        self.assertIs(generic_disposition(0.95), Disposition.QUARANTINE)


if __name__ == "__main__":
    unittest.main()
