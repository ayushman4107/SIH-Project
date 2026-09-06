"""Verify that the required data structures are present and valid."""

import argparse
import sys
from pathlib import Path


def verify_cifar10(data_root: Path) -> list[str]:
    errors = []
    cifar10_dir = data_root / "cifar-10-batches-py"
    if not cifar10_dir.is_dir():
        errors.append(f"CIFAR-10 directory not found at {cifar10_dir}")
        return errors

    required_files = [f"data_batch_{i}" for i in range(1, 6)] + ["test_batch"]
    for rf in required_files:
        file_path = cifar10_dir / rf
        if not file_path.is_file():
            errors.append(f"Missing required CIFAR-10 file: {rf}")
        elif file_path.stat().st_size == 0:
            errors.append(f"CIFAR-10 file is empty: {rf}")

    return errors


def verify_cifar100(data_root: Path) -> list[str]:
    errors = []
    cifar100_dir = data_root / "cifar-100-python"
    if cifar100_dir.is_dir():
        for rf in ["train", "test"]:
            file_path = cifar100_dir / rf
            if not file_path.is_file():
                errors.append(f"Missing required CIFAR-100 file: {rf}")
            elif file_path.stat().st_size == 0:
                errors.append(f"CIFAR-100 file is empty: {rf}")
    return errors


def verify_svhn(data_root: Path) -> list[str]:
    errors = []
    svhn_dir = data_root / "svhn"
    if svhn_dir.is_dir():
        for rf in ["train_32x32.mat", "test_32x32.mat"]:
            file_path = svhn_dir / rf
            if not file_path.is_file():
                errors.append(f"Missing required SVHN file: {rf}")
            elif file_path.stat().st_size == 0:
                errors.append(f"SVHN file is empty: {rf}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify dataset directory layout")
    parser.add_argument("--data-root", type=Path, default=Path("reference_data"))
    args = parser.parse_args()

    data_root = args.data_root
    errors = verify_cifar10(data_root) + verify_cifar100(data_root) + verify_svhn(data_root)

    if errors:
        for error in errors:
            print(f"Error: {error}", file=sys.stderr)
        return 1

    print("Data layout looks correct.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
