from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from uuid import UUID

from sentinel.core.errors import FinalizationError, ValidationError
from sentinel.utils.atomic_io import RunStager, atomic_write_json
from sentinel.utils.paths import resolve_within


class AtomicIoTests(unittest.TestCase):
    def test_json_write_and_run_finalization_are_atomic_and_write_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            report_id = UUID("28eeb4a9-f0d1-4c8b-8ac3-6fdd4206a24c")
            stager = RunStager(output, report_id)
            staging = stager.create()
            atomic_write_json(staging / "artifact.json", {"b": 2, "a": 1}, compact=True)
            self.assertEqual(json.loads((staging / "artifact.json").read_text()), {"a": 1, "b": 2})
            final = stager.finalize()
            self.assertTrue((final / "artifact.json").is_file())
            with self.assertRaises(FinalizationError):
                stager.create()

    def test_resolve_within_rejects_escape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "root"
            root.mkdir()
            (root / "inside.txt").write_text("ok", encoding="utf-8")
            self.assertEqual(resolve_within(Path("inside.txt"), root), root / "inside.txt")
            with self.assertRaises(ValidationError):
                resolve_within(Path("..") / "outside.txt", root, must_exist=False)


if __name__ == "__main__":
    unittest.main()
