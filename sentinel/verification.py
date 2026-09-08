"""Read-only verification for finalized Sentinel run directories."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sentinel.core.enums import VerificationVerdict
from sentinel.core.errors import ConfigurationError, ValidationError
from sentinel.core.schema_registry import SchemaRegistry
from sentinel.modules.inference_provenance import AuditLedger, InferenceProvenanceModule
from sentinel.utils.hashing import parse_secret_key, secure_equal, sha256_file
from sentinel.utils.paths import resolve_within


@dataclass(frozen=True)
class RunVerification:
    verdict: VerificationVerdict
    audit: dict[str, Any]
    artifacts: tuple[dict[str, Any], ...]
    provenance: tuple[dict[str, Any], ...]
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "audit": self.audit,
            "artifacts": list(self.artifacts),
            "provenance": list(self.provenance),
            "limitations": list(self.limitations),
        }


def verify_run(
    run_dir: Path, secret_value: str | None, *, expected_ledger_length: int | None = None
) -> RunVerification:
    root = run_dir.resolve(strict=True)
    registry = SchemaRegistry()
    report = json.loads((root / "assurance_report.json").read_text(encoding="utf-8"))
    coverage = json.loads((root / "coverage_statement.json").read_text(encoding="utf-8"))
    manifest = json.loads((root / "run_manifest.json").read_text(encoding="utf-8"))
    audit_entries = json.loads((root / "audit_log.json").read_text(encoding="utf-8"))
    registry.validate("assurance_report", report)
    registry.validate("coverage_statement", coverage)
    registry.validate("run_manifest", manifest)
    registry.validate("audit_log", audit_entries)

    artifact_results: list[dict[str, Any]] = []
    tampered = False
    unavailable = False
    for artifact in manifest["artifacts"]:
        if artifact["storage"] == "copied":
            try:
                path = resolve_within(Path(artifact["path"]), root, must_exist=False)
            except ValidationError as exc:
                artifact_results.append(
                    {"path": artifact["path"], "verdict": "tampered", "reason": str(exc)}
                )
                tampered = True
                continue
            if not path.is_file():
                artifact_results.append({"path": artifact["path"], "verdict": "unavailable"})
                unavailable = True
                continue
            try:
                path = resolve_within(path, root)
            except ValidationError as exc:
                artifact_results.append(
                    {"path": artifact["path"], "verdict": "tampered", "reason": str(exc)}
                )
                tampered = True
                continue
        else:
            path = Path(artifact["path"])
            if not path.is_file():
                artifact_results.append({"path": artifact["path"], "verdict": "unavailable"})
                unavailable = True
                continue
        actual = sha256_file(path)
        verdict = "valid" if secure_equal(actual, artifact["sha256"]) else "tampered"
        artifact_results.append(
            {"path": artifact["path"], "verdict": verdict, "actual_sha256": actual}
        )
        tampered |= verdict == "tampered"

    limitations: list[str] = []
    try:
        key = parse_secret_key(secret_value)
    except ConfigurationError as exc:
        key = None
        audit_result = {
            "verdict": "unavailable",
            "reason": str(exc),
            "entries": len(audit_entries),
        }
        unavailable = True
    else:
        ledger_result = AuditLedger(key, audit_entries).verify(expected_ledger_length)
        audit_result = {
            "verdict": ledger_result.verdict.value,
            "reason": ledger_result.reason,
            "entries": len(audit_entries),
        }
        tampered |= ledger_result.verdict in {
            VerificationVerdict.TAMPERED,
            VerificationVerdict.CHAIN_BROKEN,
        }
        if expected_ledger_length is None:
            limitations.append(
                "Tail completeness is unsupported without an independent expected ledger length."
            )
        if not audit_entries:
            audit_result = {
                "verdict": "unavailable",
                "reason": "run contains no authenticated audit entries",
                "entries": 0,
            }
            unavailable = True
        else:
            final = audit_entries[-1]
            if final.get("action") != "run_finalized":
                audit_result = {
                    "verdict": "chain_broken",
                    "reason": "authenticated log does not end in run_finalized",
                    "entries": len(audit_entries),
                }
                tampered = True
            else:
                payload = final.get("payload", {})
                for name, path in (
                    ("manifest_sha256", root / "run_manifest.json"),
                    ("report_sha256", root / "assurance_report.json"),
                ):
                    if not secure_equal(str(payload.get(name, "")), sha256_file(path)):
                        audit_result = {
                            "verdict": "tampered",
                            "reason": f"final audit {name} commitment mismatch",
                            "entries": len(audit_entries),
                        }
                        tampered = True

    provenance_results: list[dict[str, Any]] = []
    provenance_path = root / "artifacts" / "outputs" / "provenance_records.json"
    if provenance_path.is_file():
        records = json.loads(provenance_path.read_text(encoding="utf-8"))
        module = InferenceProvenanceModule(secret_value)
        for record in records:
            registry.validate("inference_provenance", record)
            result = module.verify(record, root)
            provenance_results.append(
                {
                    "record_id": record["record_id"],
                    "verdict": result.verdict.value,
                    "reason": result.reason,
                }
            )
            tampered |= result.verdict is VerificationVerdict.TAMPERED
            unavailable |= result.verdict is VerificationVerdict.UNAVAILABLE

    verdict = (
        VerificationVerdict.TAMPERED
        if tampered
        else VerificationVerdict.UNAVAILABLE
        if unavailable
        else VerificationVerdict.VALID
    )
    return RunVerification(
        verdict,
        audit_result,
        tuple(artifact_results),
        tuple(provenance_results),
        tuple(limitations),
    )
