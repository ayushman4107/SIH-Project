"""F5 finding aggregation, coverage disclosure, and atomic report finalization."""

from __future__ import annotations

import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from sentinel import __version__
from sentinel.core.enums import Disposition, ModuleStatus
from sentinel.core.models import Finding, ModuleAssessment, utc_now
from sentinel.core.schema_registry import SchemaRegistry
from sentinel.modules.inference_provenance import AuditLedger
from sentinel.utils.atomic_io import RunStager, atomic_write_json
from sentinel.utils.hashing import sha256_file

DISPOSITION_RANK = {
    Disposition.INCONCLUSIVE: -1,
    Disposition.ACCEPT: 0,
    Disposition.REVIEW: 1,
    Disposition.QUARANTINE: 2,
}


def overall_disposition(
    assessments: dict[str, ModuleAssessment], findings: list[Finding]
) -> tuple[Disposition, list[str]]:
    applicable = [assessment for name, assessment in assessments.items() if name != "F5"]
    if applicable and all(item.status is ModuleStatus.UNAVAILABLE for item in applicable):
        return Disposition.INCONCLUSIVE, []
    if not findings:
        return Disposition.ACCEPT, []
    highest = max((item.recommended_disposition for item in findings), key=DISPOSITION_RANK.get)
    contributors = [
        str(item.finding_id) for item in findings if item.recommended_disposition is highest
    ]
    return highest, contributors


@dataclass(frozen=True)
class FinalizedRun:
    report_id: str
    run_dir: Path
    overall_disposition: Disposition
    assurance_report: dict[str, Any]


class GovernanceModule:
    def __init__(self, registry: SchemaRegistry | None = None) -> None:
        self.registry = registry or SchemaRegistry()

    def build_coverage(
        self,
        *,
        report_id: str,
        assessments: dict[str, ModuleAssessment],
        static_manifest: dict[str, Any],
        validation_scope: dict[str, Any],
        acceptance_gates: dict[str, Any],
        additional_limitations: list[str] | None = None,
    ) -> dict[str, Any]:
        executed = sorted(
            method for assessment in assessments.values() for method in assessment.methods_executed
        )
        unavailable = [
            {"name": method.method, "reason": method.reason}
            for assessment in assessments.values()
            for method in assessment.methods_unavailable
        ]
        limitations = [
            "HMAC does not attribute records to a human or machine identity.",
            "A compromised host, process, verifier, or key holder is outside the threat model.",
            "Tail truncation is not detectable without an independent expected ledger length.",
            "Cross-session replay and trusted time are unsupported.",
            "Confidence values are uncalibrated anomaly-strength mappings, not probabilities.",
            "Unsafe arbitrary Python model pickle loading is not supported by the safe path.",
        ]
        limitations.extend(additional_limitations or [])
        return {
            "schema_version": "1.0",
            "report_id": report_id,
            "implemented_checks": list(
                dict.fromkeys(static_manifest.get("implemented_checks", []))
            ),
            "executed_checks": list(dict.fromkeys(executed)),
            "unavailable_checks": unavailable,
            "supported_attack_classes": [
                "label_errors",
                "near_duplicate_flooding",
                "embedding_outliers",
                "source_anomaly_concentration",
                "weight_spectral_anomalies",
                "protected_inference_tampering",
                "distribution_shift",
            ],
            "unsupported_attack_classes": list(
                dict.fromkeys(static_manifest.get("unsupported_attack_classes", []))
            ),
            "trust_assumptions": [
                "The Windows host, Sentinel code, Python runtime, operator, and configured "
                "reference assets are trusted.",
                "The HMAC key remains secret and source files do not change during synchronous "
                "hashing and copying.",
            ],
            "security_limitations": list(dict.fromkeys(limitations)),
            "validation_scope": validation_scope,
            "acceptance_gates": acceptance_gates,
            "trigger_scope": static_manifest.get("trigger_scope", {}),
        }

    def _manifest(
        self, staging: Path, report_id: str, model_path: Path, model_digest: str
    ) -> dict[str, Any]:
        artifacts: list[dict[str, Any]] = []
        for path in sorted(item for item in staging.rglob("*") if item.is_file()):
            relative = path.relative_to(staging).as_posix()
            if relative in {"audit_log.json", "run_manifest.json"}:
                continue
            if relative == "assurance_report.json":
                role = "report"
            elif relative == "coverage_statement.json":
                role = "coverage"
            elif relative.startswith("artifacts/inputs/"):
                role = "input"
            elif relative.startswith("artifacts/configs/"):
                role = "config"
            elif relative.startswith("artifacts/outputs/"):
                role = "output"
            else:
                role = "cache"
            artifacts.append(
                {
                    "artifact_id": str(uuid4()),
                    "role": role,
                    "storage": "copied",
                    "path": relative,
                    "sha256": sha256_file(path),
                    "size_bytes": path.stat().st_size,
                    "media_type": "application/json"
                    if path.suffix == ".json"
                    else "application/octet-stream",
                    "created_at": utc_now(),
                }
            )
        artifacts.append(
            {
                "artifact_id": str(uuid4()),
                "role": "model",
                "storage": "external",
                "path": str(model_path.resolve(strict=True)),
                "sha256": model_digest,
                "size_bytes": model_path.stat().st_size,
                "media_type": "application/octet-stream",
                "created_at": utc_now(),
            }
        )
        return {
            "schema_version": "1.0",
            "report_id": report_id,
            "created_at": utc_now(),
            "artifacts": artifacts,
        }

    def finalize(
        self,
        *,
        stager: RunStager,
        assessments: dict[str, ModuleAssessment],
        assets: dict[str, Any],
        source_assessments: list[dict[str, Any]],
        shift_assessment: dict[str, Any] | None,
        coverage_manifest: dict[str, Any],
        validation_scope: dict[str, Any],
        model_path: Path,
        model_digest: str,
        seed: int,
        ledger: AuditLedger | None,
        acceptance_gates: dict[str, Any],
        additional_limitations: list[str] | None = None,
    ) -> FinalizedRun:
        staging = stager.staging_dir
        if not staging.is_dir():
            raise ValueError("run staging directory must exist before governance finalization")
        report_id = str(stager.report_id)
        f5 = ModuleAssessment(ModuleStatus.COMPLETED, (), ("maximum_disposition_v1",), ())
        all_assessments = {**assessments, "F5": f5}
        findings = [item for assessment in all_assessments.values() for item in assessment.findings]
        disposition, contributors = overall_disposition(all_assessments, findings)
        coverage = self.build_coverage(
            report_id=report_id,
            assessments=all_assessments,
            static_manifest=coverage_manifest,
            validation_scope=validation_scope,
            acceptance_gates=acceptance_gates,
            additional_limitations=additional_limitations,
        )
        atomic_write_json(staging / "coverage_statement.json", coverage)
        report = {
            "schema_version": "1.0",
            "report_id": report_id,
            "run_timestamp": utc_now(),
            "framework_version": __version__,
            "execution": {
                "offline": True,
                "platform": "windows-x86_64",
                "python_version": platform.python_version(),
                "seed": seed,
                "run_status": "completed",
            },
            "assets": assets,
            "module_assessments": {
                name: all_assessments[name].to_report_dict()
                for name in ("F1", "F2", "F3", "F4", "F5")
            },
            "findings": [finding.to_dict() for finding in findings],
            "source_assessments": source_assessments,
            "shift_assessment": shift_assessment,
            "overall_disposition": disposition.value,
            "disposition_trace": {
                "policy": "maximum_disposition_v1",
                "contributing_finding_ids": contributors,
                "explanation": (
                    "All applicable modules were unavailable."
                    if disposition is Disposition.INCONCLUSIVE
                    else f"Maximum adverse disposition is {disposition.value}."
                ),
            },
            "coverage_statement_ref": "coverage_statement.json",
            "audit_log_ref": "audit_log.json",
            "run_manifest_ref": "run_manifest.json",
        }
        atomic_write_json(staging / "assurance_report.json", report)
        if ledger is not None:
            ledger.append(
                "disposition_computed",
                {"overall_disposition": disposition.value, "contributors": contributors},
            )
            ledger.append(
                "report_validated",
                {"report_sha256": sha256_file(staging / "assurance_report.json")},
            )
        atomic_write_json(staging / "audit_log.json", ledger.entries if ledger else [])
        manifest = self._manifest(staging, report_id, model_path, model_digest)
        atomic_write_json(staging / "run_manifest.json", manifest)
        if ledger is not None:
            ledger.append(
                "run_finalized",
                {
                    "manifest_sha256": sha256_file(staging / "run_manifest.json"),
                    "report_sha256": sha256_file(staging / "assurance_report.json"),
                },
            )
            atomic_write_json(staging / "audit_log.json", ledger.entries)
        self.registry.validate("coverage_statement", coverage)
        self.registry.validate("assurance_report", report)
        self.registry.validate("run_manifest", manifest)
        self.registry.validate("audit_log", ledger.entries if ledger else [])
        for artifact in manifest["artifacts"]:
            if artifact["storage"] == "copied":
                if sha256_file(staging / artifact["path"]) != artifact["sha256"]:
                    raise ValueError(f"artifact changed during finalization: {artifact['path']}")
        final_dir = stager.finalize()
        return FinalizedRun(report_id, final_dir, disposition, report)
