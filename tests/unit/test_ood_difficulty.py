import unittest
import numpy as np

from sentinel.modules.distribution_shift import DistributionShiftModule


class TestOODDifficulty(unittest.TestCase):
    def test_ood_difficulty_metadata(self):
        reference = np.random.randn(10, 16)
        incoming = np.random.randn(5, 16)
        
        ref_logits = np.random.randn(10, 10)
        inc_logits = np.random.randn(5, 10)
        
        module = DistributionShiftModule()
        result_easy = module.analyze(
            reference_embeddings=reference,
            incoming_embeddings=incoming,
            reference_logits=ref_logits,
            incoming_logits=inc_logits,
            ood_pair_difficulty="easy_baseline"
        )
        self.assertEqual(result_easy.ood_pair_difficulty, "easy_baseline")
        
        result_hard = module.analyze(
            reference_embeddings=reference,
            incoming_embeddings=incoming,
            reference_logits=ref_logits,
            incoming_logits=inc_logits,
            ood_pair_difficulty="hard_near_ood"
        )
        self.assertEqual(result_hard.ood_pair_difficulty, "hard_near_ood")

if __name__ == "__main__":
    unittest.main()
