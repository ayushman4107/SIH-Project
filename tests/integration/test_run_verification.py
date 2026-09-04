from __future__ import annotations

import json
import tempfile
from pathlib import Path
from uuid import uuid4

from sentinel.core.enums import ModuleStatus
from sentinel.core.models import ModuleAssessment
from sentinel.modules.governance import GovernanceModule
from sentinel.modules.inference_provenance import AuditLedger
from sentinel.utils.atomic_io import RunStager
from sentinel.utils.hashing import sha256_file
from sentinel.verification import verify_run

SECRET = "34" * 32


def _finalized_run(root: Path) -> Path:
    model = root / "model.pt"
    model.write_bytes(b"model")
    stager = RunStager(root / "output", uuid4())
    staging = stager.create()
    evidence = staging / "artifacts" / "inputs" / "sample.bin"
    evidence.parent.mkdir(parents=True)
    evidence.write_bytes(b"sample")
    assessments = {
        name: ModuleAssessment(ModuleStatus.COMPLETED) for name in ("F1", "F2", "F3", "F4")
    }
    ledger = AuditLedger(bytes.fromhex(SECRET))
    ledger.append("run_started", {"report_id": str(stager.report_id)})
    result = GovernanceModule().finalize(
        stager=stager,
        assessments=assessments,
        assets={"dataset": {}, "model": {}, "references": {}},
        source_assessments=[],
        shift_assessment=None,
        coverage_manifest={"implemented_checks": [], "unsupported_attack_classes": []},
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
    )
    return result.run_dir


def test_verifier_accepts_complete_run_and_detects_artifact_mutation() -> None:
    with tempfile.TemporaryDirectory() as directory:
        run = _finalized_run(Path(directory))
        audit_count = len(json.loads((run / "audit_log.json").read_text()))
        valid = verify_run(run, SECRET, expected_ledger_length=audit_count)
        assert valid.verdict.value == "valid"
        (run / "artifacts" / "inputs" / "sample.bin").write_bytes(b"changed")
        tampered = verify_run(run, SECRET, expected_ledger_length=audit_count)
        assert tampered.verdict.value == "tampered"


def test_verifier_exposes_tail_completeness_limitation_without_expected_length() -> None:
    with tempfile.TemporaryDirectory() as directory:
        run = _finalized_run(Path(directory))
        result = verify_run(run, SECRET)
        assert result.verdict.value == "valid"
        assert any("Tail completeness" in limitation for limitation in result.limitations)


def test_missing_copied_artifact_is_unavailable_not_tampered() -> None:
    with tempfile.TemporaryDirectory() as directory:
        run = _finalized_run(Path(directory))
        (run / "artifacts" / "inputs" / "sample.bin").unlink()
        result = verify_run(run, SECRET)
        assert result.verdict.value == "unavailable"
        missing = next(item for item in result.artifacts if item["path"].endswith("sample.bin"))
        assert missing["verdict"] == "unavailable"
