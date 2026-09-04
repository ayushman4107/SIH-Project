"""Crash-safe writes and application-level write-once run finalization."""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from sentinel.core.errors import FinalizationError


def atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    if temporary.exists():
        raise FinalizationError(f"Temporary output already exists: {temporary}")
    try:
        with temporary.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def atomic_write_json(path: Path, value: Any, *, compact: bool = False) -> None:
    separators = (",", ":") if compact else None
    text = json.dumps(
        value,
        sort_keys=True,
        separators=separators,
        ensure_ascii=False,
        allow_nan=False,
        indent=None if compact else 2,
    )
    atomic_write_bytes(path, (text + "\n").encode("utf-8"))


@dataclass
class RunStager:
    output_root: Path
    report_id: UUID

    @property
    def staging_dir(self) -> Path:
        return self.output_root / "staging" / f"{self.report_id}.partial"

    @property
    def final_dir(self) -> Path:
        return self.output_root / "runs" / str(self.report_id)

    def create(self) -> Path:
        self.output_root.mkdir(parents=True, exist_ok=True)
        (self.output_root / "staging").mkdir(exist_ok=True)
        (self.output_root / "runs").mkdir(exist_ok=True)
        if self.final_dir.exists():
            raise FinalizationError(f"Final run already exists: {self.final_dir}")
        try:
            self.staging_dir.mkdir(exist_ok=False)
        except FileExistsError as exc:
            raise FinalizationError(f"Staging run already exists: {self.staging_dir}") from exc
        return self.staging_dir

    def finalize(self) -> Path:
        if not self.staging_dir.is_dir():
            raise FinalizationError("Staging directory does not exist")
        if self.final_dir.exists():
            raise FinalizationError(f"Refusing to overwrite final run: {self.final_dir}")
        os.replace(self.staging_dir, self.final_dir)
        return self.final_dir

    def discard(self) -> None:
        if self.staging_dir.is_dir():
            shutil.rmtree(self.staging_dir)
