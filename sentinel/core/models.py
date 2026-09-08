"""Immutable domain models matching Sentinel JSON contracts."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from .enums import Disposition, FindingType, ModuleStatus, Pillar, Severity


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def wire_value(value: Any) -> Any:
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, tuple | list):
        return [wire_value(item) for item in value]
    if isinstance(value, dict):
        return {key: wire_value(item) for key, item in value.items()}
    return value


@dataclass(frozen=True)
class AssetLocator:
    asset_type: str
    asset_id: str
    sample_ids: tuple[str, ...] = ()
    source_id: str | None = None
    layer_name: str | None = None
    artifact_ref: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = wire_value(asdict(self))
        return {key: value for key, value in result.items() if value not in (None, [])}


@dataclass(frozen=True)
class MethodIdentity:
    name: str
    version: str
    parameters_digest: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {key: value for key, value in wire_value(asdict(self)).items() if value is not None}


@dataclass(frozen=True)
class Finding:
    finding_type: FindingType
    pillar: Pillar
    affected_asset: AssetLocator
    severity: Severity
    raw_score: float | int | None
    decision_threshold: float | int | str | None
    confidence: float
    confidence_normalizer: str
    human_readable_reason: str
    evidence: dict[str, Any]
    method: MethodIdentity
    recommended_disposition: Disposition
    finding_id: UUID = field(default_factory=uuid4)
    calibration_status: str = "uncalibrated"

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be within [0, 1]")
        if self.calibration_status != "uncalibrated":
            raise ValueError("Phase 2 confidence must be marked uncalibrated")

    def to_dict(self) -> dict[str, Any]:
        result = wire_value(asdict(self))
        result["affected_asset"] = self.affected_asset.to_dict()
        result["method"] = self.method.to_dict()
        return result


@dataclass(frozen=True)
class UnavailableMethod:
    method: str
    reason: str


@dataclass(frozen=True)
class ModuleAssessment:
    status: ModuleStatus
    findings: tuple[Finding, ...] = ()
    methods_executed: tuple[str, ...] = ()
    methods_unavailable: tuple[UnavailableMethod, ...] = ()

    def to_report_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "finding_count": len(self.findings),
            "methods_executed": list(self.methods_executed),
            "methods_unavailable": [wire_value(asdict(item)) for item in self.methods_unavailable],
        }


@dataclass(frozen=True)
class DatasetSample:
    sample_id: str
    image_path: Path
    label: int
    source_id: str = "unknown"
    batch_id: str | None = None


@dataclass(frozen=True)
class RunIdentity:
    report_id: UUID = field(default_factory=uuid4)
    created_at: str = field(default_factory=utc_now)
