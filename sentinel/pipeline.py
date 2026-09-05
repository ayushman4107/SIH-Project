"""Single-process F1 -> F2 -> F3 -> F4 -> F5 orchestration."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from sentinel.adapters.datasets import DatasetManifest, load_classification_manifest
from sentinel.adapters.models import ModelAdapter, load_model
from sentinel.core.enums import Disposition, FindingType, ModuleStatus, Pillar, Severity
from sentinel.core.errors import ConfigurationError, SentinelError
from sentinel.core.models import (
    AssetLocator,
    Finding,
    MethodIdentity,
    ModuleAssessment,
    UnavailableMethod,
)
from sentinel.modules.data_integrity import DataIntegrityConfig, DataIntegrityModule
from sentinel.modules.distribution_shift import DistributionShiftModule
from sentinel.modules.governance import FinalizedRun, GovernanceModule
from sentinel.modules.inference_provenance import AuditLedger, InferenceProvenanceModule
from sentinel.modules.model_integrity import ModelIntegrityModule
from sentinel.utils.atomic_io import RunStager, atomic_write_json
from sentinel.utils.config import load_config
from sentinel.utils.embeddings import EmbeddingExtractor
from sentinel.utils.hashing import parse_secret_key

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _project_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _unavailable(method: str, reason: str) -> ModuleAssessment:
    return ModuleAssessment(ModuleStatus.UNAVAILABLE, (), (), (UnavailableMethod(method, reason),))


def _engine_error(pillar: Pillar, method: str, exc: Exception) -> ModuleAssessment:
    finding = Finding(
        finding_type=FindingType.ENGINE_ERROR,
        pillar=pillar,
        affected_asset=AssetLocator("run", "current"),
        severity=Severity.HIGH,
        raw_score=None,
        decision_threshold="successful engine execution",
        confidence=0.70,
        confidence_normalizer="engine_error_policy_v1",
        human_readable_reason=f"{method} failed: {type(exc).__name__}: {exc}",
        evidence={"error_type": type(exc).__name__},
        method=MethodIdentity(method, "1"),
        recommended_disposition=Disposition.REVIEW,
    )
    return ModuleAssessment(
        ModuleStatus.FAILED, (finding,), (), (UnavailableMethod(method, str(exc)),)
    )


def _inference_transform(model_config: dict[str, Any]) -> Any:
    try:
        from torchvision import transforms
    except ImportError as exc:
        raise RuntimeError("torchvision is required for submitted-model inference") from exc
    size = tuple(model_config.get("input_size", [32, 32]))
    mean = tuple(model_config.get("mean", [0.4914, 0.4822, 0.4465]))
    std = tuple(model_config.get("std", [0.2470, 0.2435, 0.2616]))
    return transforms.Compose(
        [
            transforms.Resize(size, antialias=True),
            transforms.ToTensor(),
            transforms.Normalize(mean, std),
        ]
    )


def _logits(
    model: ModelAdapter,
    manifest: DatasetManifest,
    sample_indices: list[int],
    model_config: dict[str, Any],
) -> np.ndarray:
    import torch
    from PIL import Image

    transform = _inference_transform(model_config)
    tensors = []
    for index in sample_indices:
        with Image.open(manifest.samples[index].image_path) as image:
            tensors.append(transform(image.convert("RGB")))
    if not tensors:
        return np.empty((0, model.num_classes), dtype=np.float32)
    with torch.inference_mode():
        output = model.forward(torch.stack(tensors))
    array = output.detach().cpu().numpy().astype(np.float32, copy=False)
    if array.shape != (len(sample_indices), model.num_classes) or not np.all(np.isfinite(array)):
        raise ValueError(f"submitted model returned invalid logits shape or values: {array.shape}")
    return array


class SentinelPipeline:
    def run(self, config_path: Path) -> FinalizedRun:
        config = load_config(config_path.resolve(strict=True))
        output_root = _project_path(config["output_root"])
        stager = RunStager(output_root, __import__("uuid").uuid4())
        staging = stager.create()
        limitations: list[str] = []
        secret = os.environ.get("SENTINEL_SECRET_KEY")
        try:
            ledger: AuditLedger | None = AuditLedger(parse_secret_key(secret))
            ledger.append("run_started", {"report_id": str(stager.report_id)})
        except ConfigurationError as exc:
            ledger = None
            limitations.append(f"Authenticated audit logging unavailable: {exc}")

        dataset_root = _project_path(config["dataset_root"])
        manifest = load_classification_manifest(
            _project_path(config["dataset_manifest"]),
            dataset_root,
            config["num_classes"],
            max_image_bytes=config["resources"]["max_image_bytes"],
            max_image_pixels=config["resources"]["max_image_pixels"],
        )
        model_config = config["model"]
        model_path = _project_path(model_config["path"])
        model = load_model(
            model_path,
            model_config["format"],
            model_config["architecture_id"],
            config["num_classes"],
        )
        extractor = EmbeddingExtractor(
            _project_path(config["extractor_weights"]),
            PROJECT_ROOT / "cache" / "embeddings",
            batch_size=config["resources"]["embedding_batch_size"],
        )
        embeddings = np.stack(
            [extractor.extract_cached(sample.image_path) for sample in manifest.samples]
        )
        assessments: dict[str, ModuleAssessment] = {}

        if ledger:
            ledger.append("module_started", {"pillar": "F1"})
        try:
            f1 = DataIntegrityModule(
                DataIntegrityConfig(
                    seed=config["seed"],
                    phash_distance=config["detectors"]["phash_hamming_threshold"],
                    cosine_threshold=config["detectors"]["cosine_threshold"],
                    cosine_neighbors=config["detectors"]["cosine_neighbors"],
                    neighbor_chunk_size=config["resources"]["neighbor_chunk_size"],
                    outlier_percentile=config["detectors"]["outlier_percentile"],
                    source_p_value=config["detectors"]["source_p_value"],
                    source_rate_multiplier=config["detectors"]["source_rate_multiplier"],
                )
            ).analyze(manifest, embeddings)
            assessments["F1"] = f1.assessment
            source_assessments = list(f1.source_assessments)
        except Exception as exc:
            assessments["F1"] = _engine_error(Pillar.F1, "data_integrity", exc)
            source_assessments = []
        if ledger:
            ledger.append(
                "module_completed", {"pillar": "F1", "status": assessments["F1"].status.value}
            )

        reference_states: list[dict[str, Any]] = []
        reference_dir = _project_path(config["references"]["model_directory"])
        if reference_dir.is_dir():
            has_subdirs = any(p.is_dir() for p in reference_dir.iterdir())
            if has_subdirs:
                import logging
                logging.warning(f"Reference directory {reference_dir} contains subdirectories. They will be ignored.")
            for reference_path in sorted(reference_dir.glob("*.pt")):
                if reference_path.is_file():
                    reference_states.append(
                        load_model(
                            reference_path, "pytorch", model.architecture_id, model.num_classes
                        ).state_dict()
                    )
        try:
            # Pre-validate references to ensure none are anomalous compared to the rest
            if len(reference_states) >= 3:
                # Basic check: verify references against each other
                from sentinel.modules.model_integrity import normalized_spectra, median_spectra, spectral_score
                refs_spectra = [normalized_spectra(state) for state in reference_states]
                loo = []
                for i, r in enumerate(refs_spectra):
                    others = refs_spectra[:i] + refs_spectra[i+1:]
                    s, _ = spectral_score(r, median_spectra(others))
                    loo.append(s)
                med = float(np.median(loo))
                std = float(np.std(loo))
                # Very simple outlier detection for reference safety
                if any(s > med + 5.0 * std for s in loo):
                    import logging
                    logging.warning("One or more reference models appears anomalous; F2 results may be impacted.")
                    
            f2 = ModelIntegrityModule(
                threshold_mode=config["detectors"]["f2_threshold_mode"],
                regularized_k=config["detectors"]["f2_regularized_k"]
            ).analyze(
                candidate_state=model.state_dict(),
                reference_states=reference_states,
                architecture_id=model.architecture_id,
                candidate_id=model.digest,
            )
            assessments["F2"] = f2.assessment
        except Exception as exc:
            assessments["F2"] = _engine_error(Pillar.F2, "model_integrity", exc)
        if ledger:
            ledger.append(
                "module_completed", {"pillar": "F2", "status": assessments["F2"].status.value}
            )

        selected_ids = set(config.get("inference_sample_ids", []))
        selected = [
            index
            for index, sample in enumerate(manifest.samples)
            if sample.sample_id in selected_ids
        ]
        provenance_records: list[dict[str, Any]] = []
        f3_findings: list[Finding] = []
        incoming_logits = np.empty((0, model.num_classes), dtype=np.float32)
        if not selected:
            assessments["F3"] = _unavailable(
                "inference_provenance",
                "inference_sample_ids is empty or contains no matching samples",
            )
        else:
            try:
                incoming_logits = _logits(model, manifest, selected, model_config)
                provenance = InferenceProvenanceModule(secret)
                for position, index in enumerate(selected, start=1):
                    generated = provenance.generate(
                        input_path=manifest.samples[index].image_path,
                        model_path=model_path,
                        config=config,
                        output=incoming_logits[position - 1],
                        run_root=staging,
                        sequence_number=position,
                    )
                    provenance_records.append(generated.record)
                    if generated.record["status"] == "unsigned":
                        f3_findings.append(
                            Finding(
                                finding_type=FindingType.PROVENANCE_UNSIGNED,
                                pillar=Pillar.F3,
                                affected_asset=AssetLocator(
                                    "inference_record", generated.record["record_id"]
                                ),
                                severity=Severity.HIGH,
                                raw_score=None,
                                decision_threshold="signed",
                                confidence=0.70,
                                confidence_normalizer="unsigned_policy_v1",
                                human_readable_reason=(
                                    "Inference was released without authenticated provenance."
                                ),
                                evidence={"failure_reason": generated.record.get("failure_reason")},
                                method=MethodIdentity("inference_hmac_binding", "1"),
                                recommended_disposition=Disposition.REVIEW,
                            )
                        )
                    else:
                        verified = provenance.verify(generated.record, staging)
                        if verified.verdict.value != "valid":
                            raise RuntimeError(verified.reason)
                        if ledger:
                            ledger.append(
                                "inference_signed", {"record_id": generated.record["record_id"]}
                            )
                atomic_write_json(
                    staging / "artifacts" / "outputs" / "provenance_records.json",
                    provenance_records,
                )
                assessments["F3"] = ModuleAssessment(
                    ModuleStatus.COMPLETED,
                    tuple(f3_findings),
                    ("inference_hmac_binding", "authenticated_audit_chain"),
                    (),
                )
            except Exception as exc:
                assessments["F3"] = _engine_error(Pillar.F3, "inference_provenance", exc)
        if ledger:
            ledger.append(
                "module_completed", {"pillar": "F3", "status": assessments["F3"].status.value}
            )

        shift_assessment: dict[str, Any] | None = None
        reference_manifest_path = _project_path(config["references"]["dataset_manifest"])
        if not reference_manifest_path.is_file() or not selected:
            assessments["F4"] = _unavailable(
                "distribution_shift", "reference dataset or incoming inference batch is unavailable"
            )
        else:
            try:
                reference_manifest = load_classification_manifest(
                    reference_manifest_path, reference_manifest_path.parent, config["num_classes"]
                )
                reference_embeddings = np.stack(
                    [
                        extractor.extract_cached(sample.image_path)
                        for sample in reference_manifest.samples
                    ]
                )
                reference_logits = _logits(
                    model,
                    reference_manifest,
                    list(range(len(reference_manifest.samples))),
                    model_config,
                )
                f4 = DistributionShiftModule(
                    ood_percentile=config["detectors"]["outlier_percentile"],
                    low_ratio=config["detectors"]["entropy_low_ratio"],
                    high_ratio=config["detectors"]["entropy_high_ratio"],
                ).analyze(
                    reference_embeddings=reference_embeddings,
                    incoming_embeddings=embeddings[selected],
                    reference_logits=reference_logits,
                    incoming_logits=incoming_logits,
                    incoming_ids=[manifest.samples[index].sample_id for index in selected],
                    model_suspicious=bool(assessments["F2"].findings),
                )
                assessments["F4"] = f4.assessment
                shift_assessment = {
                    "characterization": f4.characterization,
                    "entropy_ratio": f4.entropy_ratio,
                    "reference_entropy": f4.reference_entropy,
                    "incoming_entropy": f4.incoming_entropy,
                    "model_dependency": f4.model_dependency,
                    "ood_threshold": f4.ood_threshold,
                }
            except Exception as exc:
                assessments["F4"] = _engine_error(Pillar.F4, "distribution_shift", exc)
        if ledger:
            ledger.append(
                "module_completed", {"pillar": "F4", "status": assessments["F4"].status.value}
            )

        with (PROJECT_ROOT / "configs" / "coverage_manifest.yaml").open(encoding="utf-8") as stream:
            coverage_manifest = yaml.safe_load(stream)
        assets = {
            "dataset": {"asset_id": manifest.dataset_id, "sample_count": len(manifest.samples)},
            "model": {
                "asset_id": model.digest,
                "digest": model.digest,
                "external_path": str(model_path.resolve()),
            },
            "references": {"model_count": len(reference_states)},
        }
        return GovernanceModule().finalize(
            stager=stager,
            assessments=assessments,
            assets=assets,
            source_assessments=source_assessments,
            shift_assessment=shift_assessment,
            coverage_manifest=coverage_manifest,
            validation_scope={
                "dataset": manifest.dataset_id,
                "architectures": [model.architecture_id],
                "sample_sizes": {"submitted": len(manifest.samples)},
                "seeds": [config["seed"]],
                "status": "not_run",
            },
            model_path=model_path,
            model_digest=model.digest,
            seed=config["seed"],
            ledger=ledger,
            acceptance_gates={
                "f1_label_flip_recall_floor": config["detectors"]["f1_label_flip_recall_floor"],
                "f1_duplicate_precision_floor": config["detectors"]["f1_duplicate_precision_floor"],
                "f1_outlier_auc_floor": config["detectors"]["f1_outlier_auc_floor"],
                "f3_tamper_detection_rate": config["detectors"]["f3_tamper_detection_rate"],
                "f3_replay_detection_rate": config["detectors"]["f3_replay_detection_rate"],
                "f3_mutation_detection_rate": config["detectors"]["f3_mutation_detection_rate"],
            },
            additional_limitations=limitations,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sentinel")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run", help="run all assurance pillars")
    run_parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = SentinelPipeline().run(args.config)
    except (OSError, SentinelError, ValueError, RuntimeError) as exc:
        parser.exit(2, f"sentinel: {type(exc).__name__}: {exc}\n")
    print(
        json.dumps(
            {
                "report_id": result.report_id,
                "run_dir": str(result.run_dir),
                "overall_disposition": result.overall_disposition.value,
            }
        )
    )
    return 0
