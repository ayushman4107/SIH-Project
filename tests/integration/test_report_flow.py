from __future__ import annotations

import json
import tempfile
from pathlib import Path
from uuid import uuid4

from sentinel.core.enums import Disposition, FindingType, ModuleStatus, Pillar, Severity
from sentinel.core.models import AssetLocator, Finding, MethodIdentity, ModuleAssessment
from sentinel.modules.governance import GovernanceModule
from sentinel.utils.atomic_io import RunStager
from sentinel.utils.hashing import sha256_file
from sentinel.verification import verify_run


def test_unsigned_fail_open_finalizes_as_review_without_fake_audit_protection() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        model = root / "model.pt"
        model.write_bytes(b"model")
        stager = RunStager(root / "output", uuid4())
        stager.create()
        unsigned = Finding(
            finding_type=FindingType.PROVENANCE_UNSIGNED,
            pillar=Pillar.F3,
            affected_asset=AssetLocator("inference_record", "record-1"),
            severity=Severity.HIGH,
            raw_score=None,
            decision_threshold="signed",
            confidence=0.70,
            confidence_normalizer="unsigned_policy_v1",
            human_readable_reason="Provenance key was unavailable.",
            evidence={},
            method=MethodIdentity("inference_hmac_binding", "1"),
            recommended_disposition=Disposition.REVIEW,
        )
        assessments = {
            "F1": ModuleAssessment(ModuleStatus.COMPLETED),
            "F2": ModuleAssessment(ModuleStatus.UNAVAILABLE),
            "F3": ModuleAssessment(ModuleStatus.COMPLETED, (unsigned,)),
            "F4": ModuleAssessment(ModuleStatus.UNAVAILABLE),
        }
        result = GovernanceModule().finalize(
            stager=stager,
            assessments=assessments,
            assets={"dataset": {}, "model": {}, "references": {}},
            source_assessments=[],
            shift_assessment=None,
            coverage_manifest={
                "implemented_checks": ["inference_hmac_binding"],
                "unsupported_attack_classes": [],
            },
            validation_scope={
                "dataset": "fixture",
                "architectures": ["resnet18"],
                "sample_sizes": {"submitted": 1},
                "seeds": [42],
                "status": "partial",
            },
            model_path=model,
            model_digest=sha256_file(model),
            seed=42,
            ledger=None,
            additional_limitations=["Authenticated logging unavailable in this fixture."],
        )
        assert result.overall_disposition is Disposition.REVIEW
        assert json.loads((result.run_dir / "audit_log.json").read_text()) == []
        coverage = json.loads((result.run_dir / "coverage_statement.json").read_text())
        assert any(
            "Authenticated logging unavailable" in item for item in coverage["security_limitations"]
        )
        verification = verify_run(result.run_dir, "56" * 32)
        assert verification.verdict.value == "unavailable"
        assert verification.audit["verdict"] == "unavailable"
