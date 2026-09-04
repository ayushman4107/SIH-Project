"""Path containment and Windows reparse-point defenses."""

from __future__ import annotations

import os
import stat
from pathlib import Path

from sentinel.core.errors import ValidationError


def _is_reparse_point(path: Path) -> bool:
    try:
        attributes = path.stat(follow_symlinks=False).st_file_attributes
    except AttributeError:
        return path.is_symlink()
    return bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def reject_reparse_chain(path: Path, stop_at: Path) -> None:
    current = path
    stop = stop_at.resolve(strict=True)
    while True:
        if _is_reparse_point(current):
            raise ValidationError(f"Reparse points are not allowed in protected paths: {current}")
        if current == stop:
            return
        parent = current.parent
        if parent == current:
            raise ValidationError(f"Path does not descend from allowed root: {path}")
        current = parent


def resolve_within(path: Path, root: Path, *, must_exist: bool = True) -> Path:
    root_resolved = root.resolve(strict=True)
    candidate = path if path.is_absolute() else root_resolved / path
    try:
        resolved = candidate.resolve(strict=must_exist)
    except OSError as exc:
        raise ValidationError(f"Cannot resolve path {candidate}: {exc}") from exc
    try:
        common = Path(os.path.commonpath((str(root_resolved), str(resolved))))
    except ValueError as exc:
        raise ValidationError(f"Path escapes allowed root: {path}") from exc
    if os.path.normcase(str(common)) != os.path.normcase(str(root_resolved)):
        raise ValidationError(f"Path escapes allowed root: {path}")
    if must_exist:
        reject_reparse_chain(resolved, root_resolved)
    return resolved


def safe_relative(path: Path, root: Path) -> str:
    resolved = resolve_within(path, root)
    return resolved.relative_to(root.resolve(strict=True)).as_posix()
