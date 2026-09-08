from __future__ import annotations

import unittest

from scripts.inject_label_flips import inject_flips


class FixtureScriptTests(unittest.TestCase):
    def test_label_flips_are_deterministic_and_never_keep_original_label(self) -> None:
        payload = {
            "dataset_id": "fixture",
            "samples": [
                {"sample_id": f"s{i}", "image_path": f"{i}.png", "label": i % 10}
                for i in range(100)
            ],
        }
        first, first_ids = inject_flips(payload, 0.2, 10, 42)
        second, second_ids = inject_flips(payload, 0.2, 10, 42)
        self.assertEqual(first, second)
        self.assertEqual(first_ids, second_ids)
        self.assertEqual(len(first_ids), 20)
        originals = {row["sample_id"]: row["label"] for row in payload["samples"]}
        for row in first["samples"]:
            if row["sample_id"] in first_ids:
                self.assertNotEqual(row["label"], originals[row["sample_id"]])


if __name__ == "__main__":
    unittest.main()
