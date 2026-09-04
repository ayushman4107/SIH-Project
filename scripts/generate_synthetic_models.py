"""Generate deterministic, quality-gated CIFAR-10 BadNets benchmark models."""

from __future__ import annotations

import argparse
import json
import os
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np


TARGET_CLASS = 0
INITIAL_SEEDS = (42, 43, 44, 45, 46)
CHECKERBOARD = np.array(
    [[1.0, 0.0, 1.0], [0.0, 1.0, 0.0], [1.0, 0.0, 1.0]], dtype=np.float32
)


def apply_checkerboard(image: np.ndarray) -> np.ndarray:
    """Return a copy with the exact RGB 3x3 bottom-right checkerboard applied.

    Accepted layouts are CHW or HWC with three channels. Floating images use 0/1 and
    integer images use 0/the dtype maximum.
    """
    array = np.asarray(image)
    if array.ndim != 3:
        raise ValueError("image must be a three-dimensional CHW or HWC array")
    channel_first = array.shape[0] == 3
    channel_last = array.shape[-1] == 3
    if not channel_first and not channel_last:
        raise ValueError("image must contain exactly three channels")
    result = array.copy()
    high = 1.0 if np.issubdtype(result.dtype, np.floating) else np.iinfo(result.dtype).max
    patch = (CHECKERBOARD * high).astype(result.dtype, copy=False)
    if channel_first:
        result[:, -3:, -3:] = np.broadcast_to(patch, (3, 3, 3))
    else:
        result[-3:, -3:, :] = np.repeat(patch[:, :, None], 3, axis=2)
    return result


def select_poison_indices(
    labels: np.ndarray, seed: int, poisoning_rate: float = 0.10, target_class: int = TARGET_CLASS
) -> np.ndarray:
    """Select exactly floor(rate * non-target count) deterministic non-target indices."""
    if not 0.0 <= poisoning_rate <= 1.0:
        raise ValueError("poisoning_rate must be within [0, 1]")
    candidates = np.flatnonzero(np.asarray(labels) != target_class)
    count = int(len(candidates) * poisoning_rate)
    rng = np.random.default_rng(seed)
    return np.sort(rng.choice(candidates, size=count, replace=False))


@dataclass(frozen=True)
class QualityGate:
    model_kind: str
    clean_test_accuracy: float
    triggered_target_rate: float
    accepted: bool
    reason: str | None


def evaluate_quality_gate(
    model_kind: str, clean_test_accuracy: float, triggered_target_rate: float
) -> QualityGate:
    if model_kind not in {"clean", "poisoned"}:
        raise ValueError("model_kind must be clean or poisoned")
    rate_limit = 0.20 if model_kind == "clean" else 0.80
    accuracy_ok = clean_test_accuracy >= 0.75
    rate_ok = (
        triggered_target_rate <= rate_limit
        if model_kind == "clean"
        else triggered_target_rate >= rate_limit
    )
    accepted = accuracy_ok and rate_ok
    reasons = []
    if not accuracy_ok:
        reasons.append("clean_test_accuracy_below_0.75")
    if not rate_ok:
        reasons.append("triggered_rate_gate_failed")
    return QualityGate(model_kind, clean_test_accuracy, triggered_target_rate, accepted, ";".join(reasons) or None)


@dataclass(frozen=True)
class TrainingAttempt:
    architecture_id: str
    model_kind: str
    seed: int
    epochs: int
    poison_count: int
    clean_test_accuracy: float
    triggered_target_rate: float
    accepted: bool
    reason: str | None
    artifact: str | None


def _torch_stack() -> tuple[Any, Any, Any]:
    try:
        import torch
        from torchvision import datasets, models, transforms
    except ImportError as exc:
        raise RuntimeError("PyTorch and torchvision are required for benchmark training") from exc
    return torch, (datasets, models), transforms


def _seed_everything(seed: int, torch: Any) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(True, warn_only=True)


def _stamp_tensor(tensor: Any, torch: Any) -> Any:
    result = tensor.clone()
    pattern = torch.as_tensor(CHECKERBOARD, dtype=result.dtype, device=result.device)
    result[:, -3:, -3:] = pattern.unsqueeze(0).expand(3, -1, -1)
    return result


class _BadNetsDataset:
    def __init__(
        self,
        base: Any,
        pre_transform: Any,
        normalize: Any,
        poison_indices: set[int] | None = None,
        *,
        trigger_all_non_target: bool = False,
        relabel_poisoned: bool = False,
    ) -> None:
        self.base = base
        self.pre_transform = pre_transform
        self.normalize = normalize
        self.poison_indices = poison_indices or set()
        self.trigger_all_non_target = trigger_all_non_target
        self.relabel_poisoned = relabel_poisoned

    def __len__(self) -> int:
        return len(self.base)

    def __getitem__(self, index: int) -> tuple[Any, int]:
        image, label = self.base[index]
        tensor = self.pre_transform(image)
        should_stamp = index in self.poison_indices or (
            self.trigger_all_non_target and label != TARGET_CLASS
        )
        if should_stamp:
            torch, _, _ = _torch_stack()
            tensor = _stamp_tensor(tensor, torch)
        output_label = TARGET_CLASS if index in self.poison_indices and self.relabel_poisoned else label
        return self.normalize(tensor), int(output_label)


def _architecture(name: str, models: Any) -> Any:
    if name == "resnet18":
        return models.resnet18(weights=None, num_classes=10)
    if name == "vgg16":
        return models.vgg16(weights=None, num_classes=10)
    raise ValueError(f"Unsupported benchmark architecture: {name}")


def _evaluate(model: Any, loader: Any, device: str, *, target_rate: bool = False) -> float:
    torch, _, _ = _torch_stack()
    numerator = denominator = 0
    model.eval()
    with torch.inference_mode():
        for inputs, labels in loader:
            labels = labels.to(device)
            predictions = model(inputs.to(device)).argmax(dim=1)
            if target_rate:
                mask = labels != TARGET_CLASS
                numerator += int(((predictions == TARGET_CLASS) & mask).sum().item())
                denominator += int(mask.sum().item())
            else:
                numerator += int((predictions == labels).sum().item())
                denominator += int(labels.numel())
    return numerator / denominator if denominator else 0.0


def train_attempt(
    *,
    architecture_id: str,
    model_kind: str,
    seed: int,
    data_root: Path,
    output_dir: Path,
    device: str,
    epochs: int,
    batch_size: int,
) -> TrainingAttempt:
    torch, (datasets, models), transforms = _torch_stack()
    _seed_everything(seed, torch)
    train_base = datasets.CIFAR10(data_root, train=True, download=False)
    test_base = datasets.CIFAR10(data_root, train=False, download=False)
    poison = (
        set(select_poison_indices(np.asarray(train_base.targets), seed).tolist())
        if model_kind == "poisoned"
        else set()
    )
    train_pre = transforms.Compose(
        [transforms.RandomCrop(32, padding=4), transforms.RandomHorizontalFlip(), transforms.ToTensor()]
    )
    test_pre = transforms.ToTensor()
    normalize = transforms.Normalize((0.4914, 0.4822, 0.4465), (0.2470, 0.2435, 0.2616))
    train_data = _BadNetsDataset(
        train_base, train_pre, normalize, poison, relabel_poisoned=True
    )
    clean_test = _BadNetsDataset(test_base, test_pre, normalize)
    triggered_test = _BadNetsDataset(
        test_base, test_pre, normalize, trigger_all_non_target=True
    )
    generator = torch.Generator().manual_seed(seed)
    train_loader = torch.utils.data.DataLoader(
        train_data, batch_size=batch_size, shuffle=True, num_workers=0, generator=generator
    )
    clean_loader = torch.utils.data.DataLoader(clean_test, batch_size=batch_size, num_workers=0)
    trigger_loader = torch.utils.data.DataLoader(triggered_test, batch_size=batch_size, num_workers=0)
    model = _architecture(architecture_id, models).to(device)
    optimizer = torch.optim.SGD(model.parameters(), lr=0.1, momentum=0.9, weight_decay=5e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    criterion = torch.nn.CrossEntropyLoss()
    for _ in range(epochs):
        model.train()
        for inputs, labels in train_loader:
            optimizer.zero_grad(set_to_none=True)
            loss = criterion(model(inputs.to(device)), labels.to(device))
            loss.backward()
            optimizer.step()
        scheduler.step()
    clean_accuracy = _evaluate(model, clean_loader, device)
    target_rate = _evaluate(model, trigger_loader, device, target_rate=True)
    gate = evaluate_quality_gate(model_kind, clean_accuracy, target_rate)
    artifact: str | None = None
    if gate.accepted:
        destination = output_dir / architecture_id / f"{model_kind}_seed_{seed}.pt"
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(".tmp")
        torch.save(model.state_dict(), temporary)
        os.replace(temporary, destination)
        artifact = str(destination)
    return TrainingAttempt(
        architecture_id, model_kind, seed, epochs, len(poison), clean_accuracy,
        target_rate, gate.accepted, gate.reason, artifact
    )


def _plan() -> dict[str, Any]:
    return {
        "architectures": {
            "resnet18": {"clean": 5, "poisoned": 5},
            "vgg16": {"clean": 1, "poisoned": 1},
        },
        "initial_seeds": list(INITIAL_SEEDS),
        "target_class": TARGET_CLASS,
        "poisoning_rate": 0.10,
        "trigger": CHECKERBOARD.tolist(),
        "clean_gate": {"clean_test_accuracy": 0.75, "max_triggered_target_rate": 0.20},
        "poison_gate": {"clean_test_accuracy": 0.75, "min_asr": 0.80},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("reference_data"))
    parser.add_argument("--output-dir", type=Path, default=Path("reference_models/generated"))
    parser.add_argument("--metadata", type=Path, default=Path("artifacts/benchmark_attempts.json"))
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--max-attempts-per-kind", type=int, default=30)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--dry-run", action="store_true", help="emit the frozen benchmark plan")
    args = parser.parse_args()
    if args.dry_run:
        args.metadata.parent.mkdir(parents=True, exist_ok=True)
        args.metadata.write_text(json.dumps(_plan(), indent=2), encoding="utf-8")
        print(args.metadata)
        return 0
    torch, _, _ = _torch_stack()
    device = "cuda" if args.device == "auto" and torch.cuda.is_available() else (
        "cpu" if args.device == "auto" else args.device
    )
    attempts: list[TrainingAttempt] = []
    for architecture_id, counts in _plan()["architectures"].items():
        for model_kind, required in counts.items():
            accepted = 0
            seed = INITIAL_SEEDS[0]
            attempted = 0
            while accepted < required and attempted < args.max_attempts_per_kind:
                result = train_attempt(
                    architecture_id=architecture_id, model_kind=model_kind, seed=seed,
                    data_root=args.data_root, output_dir=args.output_dir, device=device,
                    epochs=args.epochs, batch_size=args.batch_size,
                )
                attempts.append(result)
                accepted += int(result.accepted)
                attempted += 1
                seed += 1
                args.metadata.parent.mkdir(parents=True, exist_ok=True)
                args.metadata.write_text(
                    json.dumps({"plan": _plan(), "device": device, "attempts": [asdict(item) for item in attempts]}, indent=2),
                    encoding="utf-8",
                )
            if accepted < required:
                raise RuntimeError(
                    f"Only {accepted}/{required} qualifying {architecture_id} {model_kind} models "
                    f"after {attempted} deterministic attempts"
                )
    print(args.metadata)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
