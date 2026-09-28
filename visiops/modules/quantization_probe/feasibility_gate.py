from __future__ import annotations
from typing import Any
from .contracts import Stage2AResult, Stage2AReason

try:
    import onnx
except ImportError:
    onnx = None

# Ops known to lack QLinearConv-equivalent static-quantization support
# in the pinned ONNX Runtime version.
UNSUPPORTED_QUANT_OPS = {"NonMaxSuppression", "RoiAlign"}

def check_stage_2a(candidate_path: str, candidate_format: str, reference_format: str) -> Stage2AResult:
    if candidate_format == "engine":
        return Stage2AResult(available=False, reason=Stage2AReason.UNSUPPORTED_FORMAT,
                              candidate_format=candidate_format)

    if candidate_format != reference_format:
        return Stage2AResult(available=False, reason=Stage2AReason.REFERENCE_FORMAT_MISMATCH,
                              candidate_format=candidate_format)

    if candidate_format == "onnx":
        if onnx is None:
            return Stage2AResult(available=False, reason=Stage2AReason.UNSUPPORTED_FORMAT,
                                  candidate_format=candidate_format)
        model = onnx.load(candidate_path)
        op_types = {node.op_type for node in model.graph.node}
        if op_types & UNSUPPORTED_QUANT_OPS:
            return Stage2AResult(available=False, reason=Stage2AReason.UNSUPPORTED_OPS,
                                  candidate_format=candidate_format)

    return Stage2AResult(available=True, reason=Stage2AReason.NONE, candidate_format=candidate_format)
