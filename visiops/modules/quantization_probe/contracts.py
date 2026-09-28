from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

class QuantizationStatus(str, Enum):
    NORMAL_PRECISION_DRIFT = "NORMAL_PRECISION_DRIFT"
    REVIEW = "REVIEW"
    UNAVAILABLE = "UNAVAILABLE"
    QUARANTINE = "QUARANTINE"

class Stage2AReason(str, Enum):
    NONE = "none"
    UNSUPPORTED_FORMAT = "unsupported_format"          # e.g. .engine
    UNSUPPORTED_OPS = "unsupported_ops"                 # op-coverage check failed
    REFERENCE_FORMAT_MISMATCH = "reference_format_mismatch"
    PROPRIETARY_UNSUPPORTED = "proprietary_unsupported" # V7 proprietary scheme fallback

@dataclass
class Stage2AResult:
    available: bool
    reason: Stage2AReason
    candidate_format: str          # "onnx" | "pt" | "engine" | "unknown"
    candidate_precision: str = "FP32"

@dataclass
class Stage2BResult:
    status: QuantizationStatus
    mean_jsd: float
    max_jsd_z: float
    max_mse: float
    max_flip_delta: float
    degenerate_samples: int
    reference_thresholds: dict
    probe_version: str
    calibration_cache_key: str

@dataclass
class QuantizationAssessment:
    stage_2a: Stage2AResult
    stage_2b: Optional[Stage2BResult]   # None if 2A.available is False
    admitted_model_digest: Optional[str] = None
    admitted_preprocessing_digest: Optional[str] = None
