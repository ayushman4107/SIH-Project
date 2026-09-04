from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

import numpy as np

from sentinel.core.enums import VerificationVerdict
from sentinel.modules.inference_provenance import AuditLedger, InferenceProvenanceModule

SECRET = "11" * 32


class ProvenanceTests(unittest.TestCase):
    def test_generation_verification_and_output_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "input.png"
            model_path = root / "model.pt"
            input_path.write_bytes(b"encoded-image")
            model_path.write_bytes(b"model-weights")
            run = root / "run"
            run.mkdir()
            module = InferenceProvenanceModule(SECRET)
            generated = module.generate(
                input_path=input_path,
                model_path=model_path,
                config={"seed": 42},
                output=np.array([0.1, 0.9]),
                run_root=run,
                sequence_number=1,
            )
            self.assertEqual(generated.record["status"], "signed")
            self.assertEqual(
                module.verify(generated.record, run).verdict, VerificationVerdict.VALID
            )
            output_path = run / generated.record["output_ref"]
            np.save(output_path, np.array([0.2, 0.8], dtype=np.float32), allow_pickle=False)
            self.assertEqual(
                module.verify(generated.record, run).verdict, VerificationVerdict.TAMPERED
            )

    def test_missing_key_is_unsigned_and_releases_canonical_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path, model_path = root / "in.bin", root / "model.bin"
            input_path.write_bytes(b"input")
            model_path.write_bytes(b"model")
            run = root / "run"
            run.mkdir()
            generated = InferenceProvenanceModule("").generate(
                input_path=input_path,
                model_path=model_path,
                config={},
                output=[1, 2],
                run_root=run,
                sequence_number=1,
            )
            self.assertEqual(generated.record["status"], "unsigned")
            self.assertIsNone(generated.record["binding_hmac"])
            self.assertEqual(generated.released_output.dtype, np.dtype("float32"))

    def test_ledger_detects_bit_flip_deletion_and_reordering(self) -> None:
        key = bytes.fromhex(SECRET)
        ledger = AuditLedger(key)
        ledger.append("run_started", {"report_id": "r"}, timestamp="2026-01-01T00:00:00Z")
        ledger.append("module_started", {"pillar": "F1"}, timestamp="2026-01-01T00:00:01Z")
        ledger.append("module_completed", {"pillar": "F1"}, timestamp="2026-01-01T00:00:02Z")
        self.assertEqual(ledger.verify(expected_length=3).verdict, VerificationVerdict.VALID)

        changed = copy.deepcopy(ledger.entries)
        changed[1]["payload"]["pillar"] = "F2"
        self.assertEqual(AuditLedger(key, changed).verify().verdict, VerificationVerdict.TAMPERED)

        deleted = [ledger.entries[0], ledger.entries[2]]
        self.assertEqual(
            AuditLedger(key, deleted).verify().verdict, VerificationVerdict.CHAIN_BROKEN
        )

        reordered = [ledger.entries[1], ledger.entries[0], ledger.entries[2]]
        self.assertEqual(
            AuditLedger(key, reordered).verify().verdict, VerificationVerdict.CHAIN_BROKEN
        )

    def test_tail_completeness_requires_expected_length(self) -> None:
        key = bytes.fromhex(SECRET)
        ledger = AuditLedger(key)
        ledger.append("run_started", {}, timestamp="2026-01-01T00:00:00Z")
        ledger.append("run_finalized", {}, timestamp="2026-01-01T00:00:01Z")
        truncated = AuditLedger(key, ledger.entries[:1])
        self.assertEqual(truncated.verify().verdict, VerificationVerdict.VALID)
        self.assertEqual(
            truncated.verify(expected_length=2).verdict, VerificationVerdict.CHAIN_BROKEN
        )


if __name__ == "__main__":
    unittest.main()
