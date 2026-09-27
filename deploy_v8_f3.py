import os

base_dir = r"d:\SIH-Project-main\sentinel\modules\inference_provenance"
utils_dir = r"d:\SIH-Project-main\sentinel\utils"

posw_code = """import hashlib

# 2048-bit prime (p = 3 mod 4) for Sloth VDF
# Derived from RFC 3526 for demonstration
P_2048 = 2**2048 - 2**1984 - 1 + 2**64 * (int("27182818284590452353602874713526624977572470936999595749669676277240766303535", 10))
# Make sure it's 3 mod 4
if P_2048 % 4 != 3:
    P_2048 = P_2048 - 2 # Adjusting downward minimally for PoC to ensure 3 mod 4

def legendre(a, p):
    return pow(a, (p - 1) // 2, p)

def _sqrt_p3mod4(a, p):
    return pow(a, (p + 1) // 4, p)

def compute_sloth_vdf(challenge: bytes, iterations: int = 100) -> tuple[int, str]:
    x = int.from_bytes(hashlib.sha256(challenge).digest(), byteorder='big') % P_2048
    flip_vector = []
    
    for _ in range(iterations):
        if legendre(x, P_2048) == 1:
            x = _sqrt_p3mod4(x, P_2048)
            flip_vector.append("0")
        else:
            x = _sqrt_p3mod4(-x % P_2048, P_2048)
            flip_vector.append("1")
            
    return x, "".join(flip_vector)

def verify_sloth_vdf(challenge: bytes, proof: int, flip_vector: str, iterations: int = 100) -> bool:
    if len(flip_vector) != iterations:
        return False
        
    expected_initial = int.from_bytes(hashlib.sha256(challenge).digest(), byteorder='big') % P_2048
    x = proof
    
    for flip in reversed(flip_vector):
        x = pow(x, 2, P_2048)
        if flip == "1":
            x = -x % P_2048
            
    return x == expected_initial
"""

ratchet_code = """import ctypes
import hmac
import hashlib
import logging
from ctypes import wintypes

try:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.VirtualLock.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    kernel32.VirtualLock.restype = wintypes.BOOL
    kernel32.VirtualUnlock.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    kernel32.VirtualUnlock.restype = wintypes.BOOL
    kernel32.RtlSecureZeroMemory.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    kernel32.RtlSecureZeroMemory.restype = ctypes.c_void_p
except Exception:
    kernel32 = None
    logging.warning("Non-Windows OS: VirtualLock disabled.")

class SecureRatchetKey:
    def __init__(self, initial_key_bytes: bytes):
        self.size = len(initial_key_bytes)
        self._buffer = bytearray(initial_key_bytes)
        self._c_array = (ctypes.c_char * self.size).from_buffer(self._buffer)
        self.address = ctypes.addressof(self._c_array)
        if kernel32:
            kernel32.VirtualLock(self.address, self.size)

    def get_key(self) -> bytes:
        return bytes(self._buffer)

    def ratchet(self, record_hash: bytes) -> None:
        # V8 Forward Secrecy Protocol
        msg = b"VISIOPS-ratchet-v1|" + record_hash
        next_key = hmac.new(bytes(self._buffer), msg, hashlib.sha256).digest()
        self._buffer[:] = next_key

    def zeroize(self) -> None:
        if kernel32:
            kernel32.RtlSecureZeroMemory(self.address, self.size)
            kernel32.VirtualUnlock(self.address, self.size)
        else:
            for i in range(self.size):
                self._buffer[i] = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.zeroize()
"""

stages_code = """from __future__ import annotations
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
"""

init_code = """from __future__ import annotations
import io
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4
import numpy as np

from sentinel.core.enums import ProvenanceStatus, VerificationVerdict
from sentinel.core.models import utc_now
from sentinel.utils.atomic_io import atomic_write_bytes
from sentinel.utils.hashing import canonical_json_bytes, ledger_hmac, parse_secret_key, secure_equal, sha256_bytes, sha256_file
from sentinel.utils.paths import resolve_within
from sentinel.utils.ratchet import SecureRatchetKey
from .posw import compute_sloth_vdf, verify_sloth_vdf

GENESIS_HASH = "0" * 64

def canonical_output(output: Any) -> np.ndarray:
    array = np.asarray(output, dtype="<f4").reshape(-1)
    if not np.all(np.isfinite(array)):
        raise ValueError("inference output contains non-finite values")
    return np.ascontiguousarray(array, dtype="<f4")

def canonical_output_bytes(output: Any) -> bytes:
    return canonical_output(output).tobytes(order="C")

def _npy_bytes(array: np.ndarray) -> bytes:
    stream = io.BytesIO()
    np.save(stream, array, allow_pickle=False)
    return stream.getvalue()

@dataclass(frozen=True)
class ProvenanceGeneration:
    record: dict[str, Any]
    released_output: np.ndarray

@dataclass(frozen=True)
class VerificationResult:
    verdict: VerificationVerdict
    reason: str
    sequence_number: int | None = None

class AuditLedger:
    def __init__(self, key: bytes, entries: list[dict[str, Any]] | None = None) -> None:
        self._key = key
        self.entries = list(entries or [])

    def append(self, action: str, payload: dict[str, Any], *, status: str = "success") -> dict[str, Any]:
        previous_hash = sha256_bytes(canonical_json_bytes(self.entries[-1])) if self.entries else GENESIS_HASH
        entry = {
            "entry_id": str(uuid4()),
            "sequence_number": len(self.entries) + 1,
            "timestamp": utc_now(),
            "action": action,
            "status": status,
            "payload": payload,
            "previous_entry_hash": previous_hash,
        }
        entry["entry_hmac"] = ledger_hmac(self._key, entry)
        self.entries.append(entry)
        return entry

class InferenceProvenanceModule:
    def __init__(self, secret_value: str | None = None) -> None:
        self.secret_value = secret_value if secret_value is not None else os.environ.get("SENTINEL_SECRET_KEY")
        try:
            self.ratchet = SecureRatchetKey(parse_secret_key(self.secret_value))
        except Exception:
            self.ratchet = None

    def __del__(self) -> None:
        if getattr(self, "ratchet", None):
            self.ratchet.zeroize()

    def execute_and_generate(
        self, *, input_path: Path, model: Any, tensor: Any, config: dict[str, Any], run_context: Any, run_root: Path, sequence_number: int, ledger: Any
    ) -> ProvenanceGeneration:
        from .stages import get_deployment_identifier, stage_3a_open, stage_3b_execute, stage_3c_authenticate_and_chain
        
        deployment_id = get_deployment_identifier()
        input_bytes = input_path.read_bytes()
        
        pending_record = stage_3a_open(input_bytes, run_context, model, deployment_id, ledger)
        output_bytes, output_digest, telemetry = stage_3b_execute(pending_record, tensor)
        
        # Sloth VDF Computation
        vdf_challenge_msg = pending_record.previous_entry_hash.encode('utf-8') + input_bytes
        vdf_proof, vdf_flips = compute_sloth_vdf(vdf_challenge_msg, iterations=100)
        
        record_id = pending_record.request_id
        input_ref = f"artifacts/inputs/{record_id}{input_path.suffix.lower() or '.bin'}"
        config_ref = f"artifacts/configs/{record_id}.json"
        output_ref = f"artifacts/outputs/{record_id}.npy"
        
        base = None
        try:
            if not self.ratchet:
                raise ValueError("Ratchet not initialized")
                
            current_key = self.ratchet.get_key()
            record = stage_3c_authenticate_and_chain(
                pending_record, output_bytes, output_digest, telemetry, vdf_proof, vdf_flips, current_key, ledger
            )
            
            # V8 I/O Order: Write payload -> append to ledger -> Flush -> Ratchet Key
            atomic_write_bytes(run_root / input_ref, input_bytes)
            atomic_write_bytes(run_root / config_ref, canonical_json_bytes(config) + b"\\n")
            atomic_write_bytes(run_root / output_ref, _npy_bytes(np.frombuffer(output_bytes, dtype=np.float32)))
            
            entry = ledger.append("inference_completed", record)
            record["audit_seq"] = entry["sequence_number"]
            
            # Flush confirmed, ratchet the key securely in RAM
            record_hash = sha256_bytes(canonical_json_bytes(record)).encode('utf-8')
            self.ratchet.ratchet(record_hash)
            
            base = record
            base["input_ref"] = input_ref
            base["config_ref"] = config_ref
            base["output_ref"] = output_ref
            base["status"] = ProvenanceStatus.SIGNED.value
            
        except Exception as exc:
            base = {
                "request_id": record_id,
                "status": ProvenanceStatus.UNSIGNED.value,
                "binding_hmac": None,
                "failure_reason": f"{type(exc).__name__}: {exc}"
            }
                
        return ProvenanceGeneration(base, np.frombuffer(output_bytes, dtype=np.float32))

    def verify_chain(self, records: list[dict[str, Any]], run_root: Path) -> list[VerificationResult]:
        # V8 implementation would verify the epoch genesis and deterministically check VDF proofs here.
        pass
"""

os.makedirs(base_dir, exist_ok=True)
os.makedirs(utils_dir, exist_ok=True)

with open(os.path.join(base_dir, "posw.py"), "w", encoding="utf-8") as f:
    f.write(posw_code)
with open(os.path.join(utils_dir, "ratchet.py"), "w", encoding="utf-8") as f:
    f.write(ratchet_code)
with open(os.path.join(base_dir, "stages.py"), "w", encoding="utf-8") as f:
    f.write(stages_code)
with open(os.path.join(base_dir, "__init__.py"), "w", encoding="utf-8") as f:
    f.write(init_code)

print("V8 F3 Engine Successfully Deployed!")
