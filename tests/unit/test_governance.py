from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from uuid import UUID

from sentinel.core.enums import Disposition, FindingType, ModuleStatus, Pillar, Severity
from sentinel.core.models import (
    AssetLocator,
    Finding,
    MethodIdentity,
    ModuleAssessment,
    UnavailableMethod,
)
from sentinel.modules.governance import GovernanceModule, overall_disposition
from sentinel.modules.inference_provenance import AuditLedger
from sentinel.utils.atomic_io import RunStager
from sentinel.utils.hashing import sha256_file


def _finding(disposition: Disposition) -> Finding:
    return Finding(
        finding_type=FindingType.STATISTICAL_OUTLIER,
        pillar=Pillar.F1,
        affected_asset=AssetLocator("sample", "s1"),
        severity=Severity.HIGH,
        raw_score=1.0,
        decision_threshold=0.5,
        confidence=0.95 if disposition is Disposition.QUARANTINE else 0.70,
        confidence_normalizer="fixture",
        human_readable_reason="fixture",
        evidence={},
        method=MethodIdentity("fixture", "1"),
        recommended_disposition=disposition,
    )


class GovernanceTests(unittest.TestCase):
    def test_maximum_disposition_and_all_unavailable(self) -> None:
        review, quarantine = _finding(Disposition.REVIEW), _finding(Disposition.QUARANTINE)
        assessments = {
            "F1": ModuleAssessment(ModuleStatus.COMPLETED, (review, quarantine)),
            "F2": ModuleAssessment(ModuleStatus.COMPLETED),
        }
        disposition, contributors = overall_disposition(assessments, [review, quarantine])
        self.assertIs(disposition, Disposition.QUARANTINE)
        self.assertEqual(contributors, [str(quarantine.finding_id)])

        unavailable = ModuleAssessment(
            ModuleStatus.UNAVAILABLE, (), (), (UnavailableMethod("method", "missing"),)
        )
        disposition, _ = overall_disposition({"F1": unavailable, "F2": unavailable}, [])
        self.assertIs(disposition, Disposition.INCONCLUSIVE)

    def test_finalization_validates_and_commits_manifest_from_audit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "output"
            model = root / "candidate.pt"
            model.write_bytes(b"model")
            stager = RunStager(output, UUID("3bedb076-011d-4d8b-bdb4-335734906ccd"))
            staging = stager.create()
            artifact = staging / "artifacts" / "inputs" / "sample.bin"
            artifact.parent.mkdir(parents=True)
            artifact.write_bytes(b"sample")
            ledger = AuditLedger(b"k" * 32)
            ledger.append("run_started", {"report_id": str(stager.report_id)})
            assessments = {
                pillar: ModuleAssessment(ModuleStatus.COMPLETED, (), (f"method_{pillar}",), ())
                for pillar in ("F1", "F2", "F3", "F4")
            }
            result = GovernanceModule().finalize(
                stager=stager,
                assessments=assessments,
                assets={"dataset": {}, "model": {}, "references": {}},
                source_assessments=[],
                shift_assessment=None,
                coverage_manifest={
                    "implemented_checks": ["one"],
                    "unsupported_attack_classes": ["tail_truncation"],
                },
                validation_scope={
                    "dataset": "fixture",
                    "architectures": ["resnet18"],
                    "sample_sizes": {"submitted": 1},
                    "seeds": [42],
                    "status": "not_run",
                },
                model_path=model,
                model_digest=sha256_file(model),
                seed=42,
                ledger=ledger,
                acceptance_gates={},
            )
            self.assertEqual(result.overall_disposition, Disposition.ACCEPT)
            self.assertTrue(result.run_dir.is_dir())
            report = json.loads((result.run_dir / "assurance_report.json").read_text())
            manifest = json.loads((result.run_dir / "run_manifest.json").read_text())
            audit = json.loads((result.run_dir / "audit_log.json").read_text())
            self.assertEqual(report["overall_disposition"], "accept")
            self.assertFalse(
                any(item["path"] == "audit_log.json" for item in manifest["artifacts"])
            )
            self.assertEqual(audit[-1]["action"], "run_finalized")
            self.assertEqual(
                audit[-1]["payload"]["manifest_sha256"],
                sha256_file(result.run_dir / "run_manifest.json"),
            )
            self.assertEqual(
                AuditLedger(b"k" * 32, audit).verify(expected_length=len(audit)).verdict.value,
                "valid",
            )


if __name__ == "__main__":
    unittest.main()
