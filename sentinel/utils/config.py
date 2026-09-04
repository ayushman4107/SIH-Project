"""Strict configuration loading and deterministic materialization."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from sentinel.core.errors import ConfigurationError


DEFAULTS: dict[str, Any] = {
    "schema_version": "1.0",
    "seed": 42,
    "platform": "windows-x86_64",
    "task_type": "classification",
    "num_classes": 10,
    "detectors": {
        "review_threshold": 0.70,
        "quarantine_threshold": 0.95,
        "phash_hamming_threshold": 8,
        "cosine_threshold": 0.95,
        "cosine_neighbors": 10,
        "outlier_percentile": 0.95,
        "source_p_value": 0.01,
        "source_rate_multiplier": 2.0,
        "entropy_low_ratio": 0.7,
        "entropy_high_ratio": 1.3,
    },
    "resources": {
        "embedding_batch_size": 64,
        "neighbor_chunk_size": 1024,
        "max_image_bytes": 25_000_000,
        "max_image_pixels": 100_000_000,
    },
}

ALLOWED_TOP_LEVEL = set(DEFAULTS) | {
    "dataset_manifest", "dataset_root", "model", "references", "extractor_weights",
    "inference_sample_ids", "output_root",
}


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ConfigurationError(f"Configuration file does not exist: {path}")
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        loaded = json.loads(text)
    else:
        try:
            import yaml
        except ImportError as exc:
            raise ConfigurationError("PyYAML is required to read YAML configuration") from exc
        loaded = yaml.safe_load(text)
    if not isinstance(loaded, dict):
        raise ConfigurationError("Configuration root must be an object")
    unknown = sorted(set(loaded) - ALLOWED_TOP_LEVEL)
    if unknown:
        raise ConfigurationError(f"Unknown top-level configuration keys: {unknown}")
    if "secret_key" in loaded or "SENTINEL_SECRET_KEY" in loaded:
        raise ConfigurationError("HMAC secret must be supplied only through the environment")
    config = _merge(DEFAULTS, loaded)
    review = float(config["detectors"]["review_threshold"])
    quarantine = float(config["detectors"]["quarantine_threshold"])
    if not 0 <= review < quarantine <= 1:
        raise ConfigurationError("Thresholds must satisfy 0 <= review < quarantine <= 1")
    return config
