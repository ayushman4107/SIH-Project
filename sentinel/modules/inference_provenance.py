"""F3 inference binding, authenticated audit chaining, and verification."""

from __future__ import annotations

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
from sentinel.utils.hashing import (
    binding_hmac,
    canonical_json_bytes,
    ledger_hmac,
    parse_secret_key,
    secure_equal,
    sha256_bytes,
    sha256_file,
)
from sentinel.utils.paths import resolve_within
from sentinel.utils.ratchet import SecureRatchetKey

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
        if len(key) != 32:
            raise ValueError("ledger key must contain exactly 32 bytes")
        self._key = key
        self.entries: list[dict[str, Any]] = list(entries or [])

    def append(
        self,
        action: str,
        payload: dict[str, Any],
        *,
        status: str = "success",
        timestamp: str | None = None,
    ) -> dict[str, Any]:
        previous_hash = (
            sha256_bytes(canonical_json_bytes(self.entries[-1])) if self.entries else GENESIS_HASH
        )
        entry = {
            "entry_id": str(uuid4()),
            "sequence_number": len(self.entries) + 1,
            "timestamp": timestamp or utc_now(),
            "action": action,
            "actor": "sentinel-phase2",
            "status": status,
            "payload": payload,
            "previous_entry_hash": previous_hash,
        }
        entry["entry_hmac"] = ledger_hmac(self._key, entry)
        self.entries.append(entry)
        return entry

    def verify(self, expected_length: int | None = None) -> VerificationResult:
        if expected_length is not None and len(self.entries) != expected_length:
            return VerificationResult(
                VerificationVerdict.CHAIN_BROKEN, "ledger length differs from expected length"
            )
        previous_hash = GENESIS_HASH
        for expected_sequence, entry in enumerate(self.entries, start=1):
            if entry.get("sequence_number") != expected_sequence:
                return VerificationResult(
                    VerificationVerdict.CHAIN_BROKEN,
                    "sequence gap or reordering",
                    expected_sequence,
                )
            if entry.get("previous_entry_hash") != previous_hash:
                return VerificationResult(
                    VerificationVerdict.CHAIN_BROKEN, "predecessor hash mismatch", expected_sequence
                )
            supplied_hmac = entry.get("entry_hmac")
            if not isinstance(supplied_hmac, str):
                return VerificationResult(
                    VerificationVerdict.TAMPERED, "entry HMAC is missing", expected_sequence
                )
            unsigned = {key: value for key, value in entry.items() if key != "entry_hmac"}
            try:
                expected_hmac = ledger_hmac(self._key, unsigned)
            except (TypeError, ValueError) as exc:
                return VerificationResult(
                    VerificationVerdict.TAMPERED,
                    f"entry is not canonicalizable: {exc}",
                    expected_sequence,
                )
            if not secure_equal(supplied_hmac, expected_hmac):
                return VerificationResult(
                    VerificationVerdict.TAMPERED, "entry HMAC mismatch", expected_sequence
                )
            previous_hash = sha256_bytes(canonical_json_bytes(entry))
        if expected_length is None:
            return VerificationResult(
                VerificationVerdict.VALID,
                "authenticated entries are valid; tail completeness is not established",
            )
        return VerificationResult(
            VerificationVerdict.VALID, "authenticated entries and expected length are valid"
        )


class InferenceProvenanceModule:
    def __init__(self, secret_value: str | None = None) -> None:
        self.secret_value = (
            secret_value if secret_value is not None else os.environ.get("SENTINEL_SECRET_KEY")
        )
        try:
            self.ratchet = SecureRatchetKey(parse_secret_key(self.secret_value))
        except Exception:
            self.ratchet = None

    def __del__(self) -> None:
        # Best effort zeroization if the module is deleted
        if getattr(self, "ratchet", None):
            self.ratchet.zeroize()

    def generate(
        self,
        *,
        input_path: Path,
        model_path: Path,
        config: dict[str, Any],
        output: Any,
        run_root: Path,
        sequence_number: int,
    ) -> ProvenanceGeneration:
        record_id = str(uuid4())
        released = canonical_output(output)
        input_bytes = input_path.read_bytes()
        input_hash = sha256_bytes(input_bytes)
        model_hash = sha256_file(model_path)
        config_bytes = canonical_json_bytes(config)
        config_hash = sha256_bytes(config_bytes)
        output_bytes = released.tobytes(order="C")
        output_hash = sha256_bytes(output_bytes)
        input_ref = f"artifacts/inputs/{record_id}{input_path.suffix.lower() or '.bin'}"
        config_ref = f"artifacts/configs/{record_id}.json"
        output_ref = f"artifacts/outputs/{record_id}.npy"
        base = {
            "record_id": record_id,
            "sequence_number": sequence_number,
            "timestamp": utc_now(),
            "status": ProvenanceStatus.SIGNED.value,
            "input_ref": input_ref,
            "input_hash": input_hash,
            "model_path": str(model_path.resolve(strict=True)),
            "model_hash": model_hash,
            "config_ref": config_ref,
            "config_hash": config_hash,
            "output_ref": output_ref,
            "output_hash": output_hash,
            "output_contract": {
                "dtype": "float32",
                "byte_order": "little",
                "layout": "C",
                "shape": [int(released.size)],
            },
            "binding_hmac": None,
        }
        try:
            atomic_write_bytes(run_root / input_ref, input_bytes)
            atomic_write_bytes(run_root / config_ref, config_bytes + b"\n")
            atomic_write_bytes(run_root / output_ref, _npy_bytes(released))
            if not self.ratchet:
                raise ValueError("Ratchet not initialized (invalid or missing secret key)")
            current_key = self.ratchet.get_key()
            hmac_hex = binding_hmac(current_key, input_hash, model_hash, config_hash, output_hash)
            base["binding_hmac"] = hmac_hex
            self.ratchet.ratchet(hmac_hex.encode("utf-8"))
        except Exception as exc:
            base["status"] = ProvenanceStatus.UNSIGNED.value
            base["binding_hmac"] = None
            base["failure_reason"] = f"{type(exc).__name__}: {exc}"
            if getattr(self, "ratchet", None):
                self.ratchet.ratchet(b"UNSIGNED_RECORD")
        return ProvenanceGeneration(base, released)

    def verify_chain(
        self, records: list[dict[str, Any]], run_root: Path
    ) -> list[VerificationResult]:
        results = []
        try:
            root_key = parse_secret_key(self.secret_value)
        except Exception as exc:
            return [
                VerificationResult(
                    VerificationVerdict.UNAVAILABLE,
                    f"verification artifact unavailable or invalid: {exc}",
                    None,
                )
            ] * len(records)

        with SecureRatchetKey(root_key) as ratchet:
            for record in records:
                sequence = (
                    record.get("sequence_number")
                    if isinstance(record.get("sequence_number"), int)
                    else None
                )
                if record.get("status") != ProvenanceStatus.SIGNED.value:
                    results.append(
                        VerificationResult(
                            VerificationVerdict.UNAVAILABLE, "record is unsigned", sequence
                        )
                    )
                    ratchet.ratchet(b"UNSIGNED_RECORD")
                    continue
                try:
                    current_key = ratchet.get_key()
                    input_path = resolve_within(Path(record["input_ref"]), run_root)
                    config_path = resolve_within(Path(record["config_ref"]), run_root)
                    output_path = resolve_within(Path(record["output_ref"]), run_root)
                    model_path = Path(record["model_path"]).resolve(strict=True)
                    checks = {
                        "input_hash": sha256_file(input_path),
                        "model_hash": sha256_file(model_path),
                        "config_hash": sha256_bytes(
                            canonical_json_bytes(
                                json.loads(config_path.read_text(encoding="utf-8"))
                            )
                        ),
                        "output_hash": sha256_bytes(
                            canonical_output_bytes(np.load(output_path, allow_pickle=False))
                        ),
                    }
                    tampered_field = None
                    for field, actual in checks.items():
                        if not secure_equal(str(record.get(field, "")), actual):
                            tampered_field = field
                            break

                    if tampered_field:
                        results.append(
                            VerificationResult(
                                VerificationVerdict.TAMPERED, f"{tampered_field} mismatch", sequence
                            )
                        )
                        hmac_val = record.get("binding_hmac")
                        ratchet.ratchet(
                            hmac_val.encode("utf-8")
                            if isinstance(hmac_val, str)
                            else b"UNSIGNED_RECORD"
                        )
                        continue

                    expected_binding = binding_hmac(
                        current_key,
                        checks["input_hash"],
                        checks["model_hash"],
                        checks["config_hash"],
                        checks["output_hash"],
                    )
                    record_hmac = str(record.get("binding_hmac", ""))
                    if not secure_equal(record_hmac, expected_binding):
                        results.append(
                            VerificationResult(
                                VerificationVerdict.TAMPERED, "binding HMAC mismatch", sequence
                            )
                        )
                    else:
                        results.append(
                            VerificationResult(
                                VerificationVerdict.VALID,
                                "component hashes and binding HMAC are valid",
                                sequence,
                            )
                        )
                    ratchet.ratchet(record_hmac.encode("utf-8"))
                except (OSError, KeyError, TypeError, ValueError) as exc:
                    results.append(
                        VerificationResult(
                            VerificationVerdict.UNAVAILABLE,
                            f"verification artifact unavailable or invalid: {exc}",
                            sequence,
                        )
                    )
                    hmac_val = record.get("binding_hmac")
                    ratchet.ratchet(
                        hmac_val.encode("utf-8")
                        if isinstance(hmac_val, str)
                        else b"UNSIGNED_RECORD"
                    )
        return results
