"""Allowlisted PyTorch and TorchScript model adapters."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from sentinel.core.enums import ModelFormat
from sentinel.core.errors import CapabilityDeferredError, ValidationError
from sentinel.utils.hashing import sha256_file


class ModelProtocol(Protocol):
    def __call__(self, inputs: Any) -> Any: ...
    def state_dict(self) -> dict[str, Any]: ...


@dataclass
class ModelAdapter:
    model: ModelProtocol
    model_path: Path
    model_format: ModelFormat
    architecture_id: str
    num_classes: int
    access_level: str
    digest: str

    def forward(self, input_batch: Any) -> Any:
        return self.model(input_batch)

    def state_dict(self) -> dict[str, Any]:
        if self.access_level != "white_box":
            raise ValidationError("state_dict is unavailable for black-box access")
        return dict(self.model.state_dict())


def _torch_modules() -> tuple[Any, Any]:
    try:
        import torch
        from torchvision import models
    except ImportError as exc:
        raise ValidationError("PyTorch and torchvision are required for model loading") from exc
    return torch, models


def _architecture(architecture_id: str, num_classes: int) -> Any:
    _, models = _torch_modules()
    if architecture_id == "resnet18":
        return models.resnet18(weights=None, num_classes=num_classes)
    if architecture_id == "vgg16":
        return models.vgg16(weights=None, num_classes=num_classes)
    raise ValidationError(f"Architecture is not allowlisted: {architecture_id}")


def load_pytorch_state_dict(path: Path, architecture_id: str, num_classes: int) -> ModelAdapter:
    torch, _ = _torch_modules()
    resolved = path.resolve(strict=True)
    model = _architecture(architecture_id, num_classes)
    try:
        payload = torch.load(resolved, map_location="cpu", weights_only=True)
    except TypeError as exc:
        raise ValidationError("Installed torch lacks safe weights_only loading") from exc
    state = payload.get("state_dict", payload) if isinstance(payload, dict) else payload
    if not isinstance(state, dict):
        raise ValidationError("PyTorch artifact does not contain a state dictionary")
    model.load_state_dict(state, strict=True)
    model.eval()
    return ModelAdapter(
        model,
        resolved,
        ModelFormat.PYTORCH,
        architecture_id,
        num_classes,
        "white_box",
        sha256_file(resolved),
    )


def load_torchscript(path: Path, architecture_id: str, num_classes: int) -> ModelAdapter:
    torch, _ = _torch_modules()
    resolved = path.resolve(strict=True)
    model = torch.jit.load(str(resolved), map_location="cpu")
    model.eval()
    return ModelAdapter(
        model,
        resolved,
        ModelFormat.TORCHSCRIPT,
        architecture_id,
        num_classes,
        "white_box",
        sha256_file(resolved),
    )


def load_model(
    path: Path, model_format: str, architecture_id: str, num_classes: int
) -> ModelAdapter:
    if model_format == ModelFormat.PYTORCH.value:
        return load_pytorch_state_dict(path, architecture_id, num_classes)
    if model_format == ModelFormat.TORCHSCRIPT.value:
        return load_torchscript(path, architecture_id, num_classes)
    if model_format == ModelFormat.ONNX.value:
        raise CapabilityDeferredError("ONNX execution")
    raise ValidationError(f"Unsupported model format: {model_format}")
