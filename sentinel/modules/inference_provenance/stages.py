from __future__ import annotations
import os
import socket
import time
import uuid
import json
from dataclasses import dataclass
from typing import Any

from sentinel import __version__
from sentinel.utils.hashing import sha256_bytes, hmac_sha256, canonical_json_bytes

@dataclass
class PendingInferenceRecord:
    request_id: str
    opened_at_unix: float
    input_bytes_digest: str
    admitted_model_id: str
    admission_source: str
    admitted_preprocessing_digest: str
    deployment_identifier: dict
    loaded_model_ref: Any
    audit_seq_opened: int
    previous_entry_hash: str

def get_deployment_identifier() -> dict:
    return {
        "hostname": socket.gethostname(),
        "sentinel_version": __version__,
        "process_id": os.getpid(),
        "process_started_at_unix": time.time(),
    }

def stage_3a_open(
    input_bytes: bytes,
    run_context: Any,
    loaded_model: Any,
    deployment_identifier: dict,
    ledger: Any,
) -> PendingInferenceRecord:
    model_id = getattr(run_context, "admitted_model_digest", "unknown")
    admission_source = "F2_PINNED" if model_id != "unknown" else "INDEPENDENTLY_DERIVED"
    preprocessing_digest = getattr(run_context, "admitted_preprocessing_digest", sha256_bytes(canonical_json_bytes({})))
    request_id = str(uuid.uuid4())
    input_digest = sha256_bytes(input_bytes)
    
    entry = ledger.append("inference_opened", {
        "request_id": request_id,
        "input_digest": input_digest,
        "admitted_model_id": model_id,
    })
    
    return PendingInferenceRecord(
        request_id=request_id,
        opened_at_unix=time.time(),
        input_bytes_digest=input_digest,
        admitted_model_id=model_id,
        admission_source=admission_source,
        admitted_preprocessing_digest=preprocessing_digest,
        deployment_identifier=deployment_identifier,
        loaded_model_ref=loaded_model,
        audit_seq_opened=entry["sequence_number"],
        previous_entry_hash=entry["previous_entry_hash"]
    )

def stage_3b_execute(pending: PendingInferenceRecord, preprocessed_input: Any) -> tuple[bytes, str, dict]:
    telemetry = {"engine": "UNKNOWN"}
    start_ns = time.perf_counter_ns()
    
    if hasattr(pending.loaded_model_ref, "forward"):
        import torch
        telemetry["engine"] = "PyTorch"
        with torch.inference_mode():
            output = pending.loaded_model_ref.forward(preprocessed_input)
        if torch.cuda.is_available():
            telemetry["global_context_peak_memory"] = torch.cuda.max_memory_allocated()
        
        # Need to cast tensor to numpy for bytes
        if hasattr(output, "detach"):
            output = output.detach().cpu().numpy()
    else:
        telemetry["engine"] = "ONNX"
        input_name = pending.loaded_model_ref.get_inputs()[0].name
        output = pending.loaded_model_ref.run(None, {input_name: preprocessed_input})[0]
        telemetry["global_context_peak_memory"] = "UNAVAILABLE_NATIVE_TRACE"
        
    duration_ns = time.perf_counter_ns() - start_ns
    telemetry["execution_duration_ns"] = duration_ns
    
    from . import canonical_output_bytes
    output_bytes = canonical_output_bytes(output)
    return output_bytes, sha256_bytes(output_bytes), telemetry

def stage_3c_authenticate_and_chain(
    pending: PendingInferenceRecord,
    output_bytes: bytes,
    output_digest: str,
    telemetry: dict,
    vdf_proof: int,
    vdf_flips: str,
    current_key: bytes,
    ledger: Any,
) -> dict:
    nonce = str(uuid.uuid4())
    deployment_json = canonical_json_bytes(pending.deployment_identifier).decode('utf-8')
    telemetry_json = canonical_json_bytes(telemetry).decode('utf-8')
    
    message = "|".join([
        "v8",
        pending.request_id,
        pending.input_bytes_digest,
        pending.admitted_model_id,
        deployment_json,
        telemetry_json,
        output_digest,
        str(vdf_proof),
        vdf_flips,
        nonce
    ]).encode('utf-8')
    
    binding_mac = hmac_sha256(current_key, b"binding|", message)
    
    record = {
        "request_id": pending.request_id,
        "input_digest": pending.input_bytes_digest,
        "admitted_model_id": pending.admitted_model_id,
        "deployment_identifier": pending.deployment_identifier,
        "telemetry": telemetry,
        "output_digest": output_digest,
        "vdf_proof": str(vdf_proof),
        "vdf_flips": vdf_flips,
        "nonce": nonce,
        "binding_hmac": binding_mac,
        "binding_format_version": "v8",
        "opened_seq": pending.audit_seq_opened,
    }
    return record
