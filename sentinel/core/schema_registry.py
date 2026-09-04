"""Offline loading and validation of bundled JSON Schemas."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .errors import ValidationError


SCHEMA_FILES = {
    "finding": "finding.schema.json",
    "assurance_report": "assurance-report.schema.json",
    "inference_provenance": "inference-provenance.schema.json",
    "audit_log": "audit-log.schema.json",
    "coverage_statement": "coverage-statement.schema.json",
    "run_manifest": "run-manifest.schema.json",
}


class SchemaRegistry:
    def __init__(self, schema_root: Path | None = None) -> None:
        self.schema_root = schema_root or Path(__file__).resolve().parents[2] / "schemas"
        self._schemas = {
            name: json.loads((self.schema_root / filename).read_text(encoding="utf-8"))
            for name, filename in SCHEMA_FILES.items()
        }

    def get(self, name: str) -> dict[str, Any]:
        try:
            return self._schemas[name]
        except KeyError as exc:
            raise ValidationError(f"Unknown schema {name!r}") from exc

    def validate(self, name: str, instance: Any) -> None:
        try:
            from jsonschema import Draft202012Validator, FormatChecker
            from referencing import Registry, Resource
        except ImportError as exc:
            raise ValidationError("jsonschema is required for contract validation") from exc
        registry = Registry()
        for schema in self._schemas.values():
            registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
        validator = Draft202012Validator(
            self.get(name), registry=registry, format_checker=FormatChecker()
        )
        errors = sorted(validator.iter_errors(instance), key=lambda err: list(err.path))
        if errors:
            first = errors[0]
            location = ".".join(str(part) for part in first.absolute_path) or "$"
            raise ValidationError(f"{name} schema violation at {location}: {first.message}")
