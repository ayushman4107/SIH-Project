"""Occurrence-preserving classification dataset manifests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

from sentinel.core.errors import CapabilityDeferredError, ValidationError
from sentinel.core.models import DatasetSample
from sentinel.utils.paths import resolve_within


@dataclass(frozen=True)
class DatasetManifest:
    dataset_id: str
    root: Path
    samples: tuple[DatasetSample, ...]
    num_classes: int


def _load_rows(path: Path) -> tuple[str, list[dict[str, Any]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return path.stem, payload
    if isinstance(payload, dict) and isinstance(payload.get("samples"), list):
        return str(payload.get("dataset_id") or path.stem), payload["samples"]
    raise ValidationError("Dataset manifest must be an array or an object containing samples")


def _validate_image(path: Path, max_bytes: int, max_pixels: int) -> None:
    if path.stat().st_size > max_bytes:
        raise ValidationError(f"Image exceeds configured byte limit: {path}")
    try:
        with Image.open(path) as image:
            width, height = image.size
            if width * height > max_pixels:
                raise ValidationError(f"Image exceeds configured pixel limit: {path}")
            image.verify()
    except ValidationError:
        raise
    except Exception as exc:
        raise ValidationError(f"Unreadable image {path}: {exc}") from exc


def load_classification_manifest(
    manifest_path: Path,
    dataset_root: Path,
    num_classes: int,
    *,
    max_image_bytes: int = 25_000_000,
    max_image_pixels: int = 100_000_000,
) -> DatasetManifest:
    manifest_resolved = manifest_path.resolve(strict=True)
    root_resolved = dataset_root.resolve(strict=True)
    dataset_id, rows = _load_rows(manifest_resolved)
    if not rows:
        raise ValidationError("Dataset manifest is empty")
    if num_classes < 2:
        raise ValidationError("num_classes must be at least 2")
    samples: list[DatasetSample] = []
    seen_ids: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValidationError(f"Sample at index {index} must be an object")
        sample_id = row.get("sample_id")
        label = row.get("label")
        image_path = row.get("image_path")
        if not isinstance(sample_id, str) or not sample_id:
            raise ValidationError(f"Sample at index {index} has an invalid sample_id")
        if sample_id in seen_ids:
            raise ValidationError(f"Duplicate sample_id: {sample_id}")
        if not isinstance(label, int) or isinstance(label, bool) or not 0 <= label < num_classes:
            raise ValidationError(f"Sample {sample_id} has an invalid label")
        if not isinstance(image_path, str) or not image_path:
            raise ValidationError(f"Sample {sample_id} has an invalid image_path")
        resolved_image = resolve_within(Path(image_path), root_resolved)
        if not resolved_image.is_file():
            raise ValidationError(f"Sample image is not a file: {resolved_image}")
        _validate_image(resolved_image, max_image_bytes, max_image_pixels)
        seen_ids.add(sample_id)
        samples.append(
            DatasetSample(
                sample_id=sample_id,
                image_path=resolved_image,
                label=label,
                source_id=str(row.get("source_id") or "unknown"),
                batch_id=str(row["batch_id"]) if row.get("batch_id") is not None else None,
            )
        )
    return DatasetManifest(dataset_id, root_resolved, tuple(samples), num_classes)


def load_detection_manifest(*_: Any, **__: Any) -> DatasetManifest:
    raise CapabilityDeferredError("COCO/YOLO object detection")


def load_segmentation_manifest(*_: Any, **__: Any) -> DatasetManifest:
    raise CapabilityDeferredError("segmentation")
