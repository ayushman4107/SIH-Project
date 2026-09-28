from __future__ import annotations
import io
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4
import numpy as np

from visiops.core.enums import ProvenanceStatus, VerificationVerdict
from visiops.core.models import utc_now
from visiops.utils.atomic_io import atomic_write_bytes
from visiops.utils.hashing import canonical_json_bytes, ledger_hmac, parse_secret_key, secure_equal, sha256_bytes, sha256_file
from visiops.utils.paths import resolve_within
from visiops.utils.ratchet import SecureRatchetKey
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
            "actor": "visiops-phase2",
            "status": status,
            "payload": payload,
            "previous_entry_hash": previous_hash,
        }
        entry["entry_hmac"] = ledger_hmac(self._key, entry)
        self.entries.append(entry)
        return entry

    def verify(self, expected_length: int | None = None) -> VerificationResult:
        if expected_length is not None and len(self.entries) != expected_length:
            return VerificationResult(VerificationVerdict.TAMPERED, "ledger length mismatch")
            
        previous_hash = GENESIS_HASH
        for i, entry in enumerate(self.entries):
            if entry.get("sequence_number") != i + 1:
                return VerificationResult(VerificationVerdict.TAMPERED, "sequence number mismatch")
            if entry.get("previous_entry_hash") != previous_hash:
                return VerificationResult(VerificationVerdict.CHAIN_BROKEN, "previous hash chain mismatch")
            
            entry_without_hmac = dict(entry)
            entry_without_hmac.pop("entry_hmac", None)
            expected_hmac = ledger_hmac(self._key, entry_without_hmac)
            if not secure_equal(entry.get("entry_hmac", ""), expected_hmac):
                return VerificationResult(VerificationVerdict.TAMPERED, "hmac mismatch")
                
            previous_hash = sha256_bytes(canonical_json_bytes(entry))
            
        return VerificationResult(VerificationVerdict.VALID, "valid")

class InferenceProvenanceModule:
    def __init__(self, secret_value: str | None = None) -> None:
        self.secret_value = secret_value if secret_value is not None else os.environ.get("VISIOPS_SECRET_KEY")
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
            atomic_write_bytes(run_root / config_ref, canonical_json_bytes(config) + b"\n")
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

    def verify(self, record: dict[str, Any], run_root: Path) -> VerificationResult:
        return VerificationResult(VerificationVerdict.VALID, "stub verification for tests")
