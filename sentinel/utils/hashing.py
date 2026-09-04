"""Canonical JSON, SHA-256, and domain-separated HMAC primitives."""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
from typing import Any, BinaryIO

from sentinel.core.errors import ConfigurationError


HASH_CHUNK_SIZE = 1024 * 1024


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_stream(stream: BinaryIO, chunk_size: int = HASH_CHUNK_SIZE) -> str:
    digest = hashlib.sha256()
    while chunk := stream.read(chunk_size):
        digest.update(chunk)
    return digest.hexdigest()


def sha256_file(path: Path, chunk_size: int = HASH_CHUNK_SIZE) -> str:
    with path.open("rb") as stream:
        return sha256_stream(stream, chunk_size)


def parse_secret_key(value: str | None) -> bytes:
    if value is None:
        raise ConfigurationError("SENTINEL_SECRET_KEY is not set")
    if len(value) != 64:
        raise ConfigurationError("SENTINEL_SECRET_KEY must contain exactly 64 hex characters")
    try:
        key = bytes.fromhex(value)
    except ValueError as exc:
        raise ConfigurationError("SENTINEL_SECRET_KEY must contain only hexadecimal characters") from exc
    if len(key) != 32:
        raise ConfigurationError("SENTINEL_SECRET_KEY must decode to exactly 32 bytes")
    return key


def hmac_sha256(key: bytes, domain: bytes, message: bytes) -> str:
    if domain not in {b"binding|", b"ledger|"}:
        raise ValueError("unrecognized HMAC domain")
    return hmac.new(key, domain + message, hashlib.sha256).hexdigest()


def binding_hmac(
    key: bytes,
    input_hash: str,
    model_hash: str,
    config_hash: str,
    output_hash: str,
) -> str:
    message = "|".join((input_hash, model_hash, config_hash, output_hash)).encode("utf-8")
    return hmac_sha256(key, b"binding|", message)


def ledger_hmac(key: bytes, entry_without_hmac: dict[str, Any]) -> str:
    return hmac_sha256(key, b"ledger|", canonical_json_bytes(entry_without_hmac))


def secure_equal(left: str, right: str) -> bool:
    return hmac.compare_digest(left, right)
