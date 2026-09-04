"""Verify a finalized Sentinel run without modifying it."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from sentinel.verification import verify_run


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--expected-ledger-length", type=int)
    args = parser.parse_args()
    result = verify_run(
        args.run_dir,
        os.environ.get("SENTINEL_SECRET_KEY"),
        expected_ledger_length=args.expected_ledger_length,
    )
    print(json.dumps(result.to_dict(), indent=2))
    return 0 if result.verdict.value == "valid" else 2


if __name__ == "__main__":
    raise SystemExit(main())
