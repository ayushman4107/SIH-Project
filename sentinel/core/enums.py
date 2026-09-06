"""Stable enums whose values are their JSON wire representation."""

from enum import Enum


class WireEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class Pillar(WireEnum):
    F1 = "F1"
    F2 = "F2"
    F3 = "F3"
    F4 = "F4"
    F5 = "F5"


class Disposition(WireEnum):
    ACCEPT = "accept"
    REVIEW = "review"
    QUARANTINE = "quarantine"
    INCONCLUSIVE = "inconclusive"


class Severity(WireEnum):
    INFORMATIONAL = "informational"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ModuleStatus(WireEnum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


class TaskType(WireEnum):
    CLASSIFICATION = "classification"
    OBJECT_DETECTION = "object_detection"
    SEGMENTATION = "segmentation"


class ModelFormat(WireEnum):
    PYTORCH = "pytorch"
    TORCHSCRIPT = "torchscript"
    ONNX = "onnx"


class ProvenanceStatus(WireEnum):
    SIGNED = "signed"
    UNSIGNED = "unsigned"


class VerificationVerdict(WireEnum):
    VALID = "valid"
    TAMPERED = "tampered"
    CHAIN_BROKEN = "chain_broken"
    UNAVAILABLE = "unavailable"
    UNSUPPORTED = "unsupported"


class FindingType(WireEnum):
    LABEL_ERROR = "label_error"
    NEAR_DUPLICATE = "near_duplicate"
    STATISTICAL_OUTLIER = "statistical_outlier"
    SOURCE_CONCENTRATION = "source_concentration"
    WEIGHT_SPECTRAL_ANOMALY = "weight_spectral_anomaly"
    NON_FINITE_WEIGHT = "non_finite_weight"
    PROVENANCE_TAMPERED = "provenance_tampered"
    PROVENANCE_REORDERED = "provenance_reordered"
    PROVENANCE_DELETED = "provenance_deleted"
    PROVENANCE_UNSIGNED = "provenance_unsigned"
    OOD_SAMPLE = "ood_sample"
    POSSIBLE_DRIFT = "possible_drift"
    SUSPICIOUS_ENTROPY_SHIFT = "suspicious_entropy_shift"
    ENGINE_ERROR = "engine_error"
    MALFORMED_INPUT = "malformed_input"
    ACTIVATION_CLUSTER_ANOMALY = "activation_cluster_anomaly"
    GRADIENT_MISALIGNMENT = "gradient_misalignment"
    INFLUENCE_SYSTEMATIC_MISLABEL = "influence_systematic_mislabel"
