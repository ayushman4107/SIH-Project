"""Deterministic frozen ResNet-18 embedding extraction and cache identities."""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image

from sentinel.core.errors import ValidationError
from sentinel.utils.hashing import canonical_json_bytes, sha256_bytes, sha256_file


IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)
EXTRACTOR_VERSION = "resnet18_gap_v1"


def embedding_cache_key(image_path: Path, weights_path: Path, preprocessing: dict) -> str:
    identity = {
        "image_sha256": sha256_file(image_path),
        "weights_sha256": sha256_file(weights_path),
        "preprocessing": preprocessing,
        "extractor_version": EXTRACTOR_VERSION,
    }
    return sha256_bytes(canonical_json_bytes(identity))


def _atomic_save_npy(path: Path, array: np.ndarray) -> None:
    buffer = io.BytesIO()
    np.save(buffer, array, allow_pickle=False)
    from sentinel.utils.atomic_io import atomic_write_bytes

    atomic_write_bytes(path, buffer.getvalue())


@dataclass
class EmbeddingExtractor:
    weights_path: Path
    cache_dir: Path | None = None
    batch_size: int = 64
    device: str = "cpu"

    def __post_init__(self) -> None:
        try:
            import torch
            from torchvision import models, transforms
        except ImportError as exc:
            raise ValidationError("PyTorch and torchvision are required for embeddings") from exc
        model = models.resnet18(weights=None)
        state = torch.load(self.weights_path.resolve(strict=True), map_location="cpu", weights_only=True)
        if isinstance(state, dict) and "state_dict" in state:
            state = state["state_dict"]
        model.load_state_dict(state, strict=True)
        model.fc = torch.nn.Identity()
        model.eval().to(self.device)
        self._torch = torch
        self._model = model
        self._transform = transforms.Compose(
            [
                transforms.Resize((224, 224), antialias=True),
                transforms.ToTensor(),
                transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
            ]
        )
        self.preprocessing = {
            "resize": [224, 224], "antialias": True, "mean": IMAGENET_MEAN, "std": IMAGENET_STD
        }

    def extract(self, image_paths: Iterable[Path]) -> np.ndarray:
        paths = list(image_paths)
        if not paths:
            return np.empty((0, 512), dtype=np.float32)
        vectors: list[np.ndarray] = []
        for start in range(0, len(paths), self.batch_size):
            tensors = []
            for path in paths[start : start + self.batch_size]:
                with Image.open(path) as image:
                    tensors.append(self._transform(image.convert("RGB")))
            batch = self._torch.stack(tensors).to(self.device)
            with self._torch.inference_mode():
                output = self._model(batch)
            vectors.append(output.detach().cpu().numpy().astype("<f4", copy=False))
        result = np.ascontiguousarray(np.concatenate(vectors, axis=0), dtype="<f4")
        if result.shape != (len(paths), 512):
            raise ValidationError(f"Unexpected embedding shape: {result.shape}")
        return result

    def extract_cached(self, image_path: Path) -> np.ndarray:
        if self.cache_dir is None:
            return self.extract([image_path])[0]
        key = embedding_cache_key(image_path, self.weights_path, self.preprocessing)
        destination = self.cache_dir / f"{key}.npy"
        if destination.is_file():
            cached = np.load(destination, allow_pickle=False)
            if cached.shape == (512,) and cached.dtype == np.dtype("<f4"):
                return cached
        vector = self.extract([image_path])[0]
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        _atomic_save_npy(destination, vector)
        return vector
