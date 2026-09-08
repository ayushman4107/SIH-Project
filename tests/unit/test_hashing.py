from __future__ import annotations

import hashlib
import hmac
import math
import tempfile
import unittest
from pathlib import Path

from sentinel.core.errors import ConfigurationError
from sentinel.utils.hashing import (
    binding_hmac,
    canonical_json_bytes,
    ledger_hmac,
    parse_secret_key,
    sha256_file,
)


class HashingTests(unittest.TestCase):
    def test_canonical_json_is_sorted_compact_utf8(self) -> None:
        self.assertEqual(canonical_json_bytes({"z": "é", "a": 1}), b'{"a":1,"z":"\xc3\xa9"}')
        with self.assertRaises(ValueError):
            canonical_json_bytes({"bad": math.nan})

    def test_secret_key_is_exactly_32_bytes_of_hex(self) -> None:
        self.assertEqual(parse_secret_key("ab" * 32), bytes.fromhex("ab" * 32))
        for invalid in (None, "ab", "zz" * 32):
            with self.assertRaises(ConfigurationError):
                parse_secret_key(invalid)

    def test_binding_vector_uses_exact_domain_and_separator(self) -> None:
        key = bytes(range(32))
        values = ("01" * 32, "02" * 32, "03" * 32, "04" * 32)
        expected = hmac.new(
            key, ("binding|" + "|".join(values)).encode(), hashlib.sha256
        ).hexdigest()
        self.assertEqual(binding_hmac(key, *values), expected)

    def test_ledger_hmac_covers_all_supplied_fields(self) -> None:
        key = b"k" * 32
        first = ledger_hmac(key, {"sequence_number": 1, "payload": {"x": 1}})
        second = ledger_hmac(key, {"sequence_number": 2, "payload": {"x": 1}})
        self.assertNotEqual(first, second)

    def test_file_hash_streams_correctly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "asset.bin"
            path.write_bytes(b"sentinel" * 1000)
            expected = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(sha256_file(path, chunk_size=17), expected)


if __name__ == "__main__":
    unittest.main()
