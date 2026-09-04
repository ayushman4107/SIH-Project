# Sentinel CV Assurance

Sentinel is a local, offline computer-vision integrity assurance prototype for SIH Problem
Statement 26228. It evaluates classification datasets, white-box model weights, generated
inference evidence, and distribution shift before producing a transparent governance
disposition: `accept`, `review`, `quarantine`, or `inconclusive`.

This repository implements the Phase 2 baseline. It is a single Python process with no
frontend, network service, database, project-owned IPC, or mandatory retraining of submitted
models.

## Assurance pillars

- F1: CleanLab label issues, pHash/cosine duplicates, Isolation Forest outliers, and
  contributor/source concentration.
- F2: same-architecture per-layer SVD spectra, Wasserstein distances, leave-one-out clean
  calibration, and a `nextafter` maximum-clean threshold.
- F3: exact input/model/config/output SHA-256 binding, HMAC-SHA256 provenance, authenticated
  audit chaining, read-only verification, and explicit `UNSIGNED` fail-open behavior.
- F4: Ledoit-Wolf Mahalanobis OOD scores and submitted-model predictive-entropy ratios.
- F5: canonical findings, fixed policy exceptions, maximum-disposition aggregation,
  coverage disclosure, and atomic application-level write-once reports.

The complete governing documents are under [`docs/phase2`](docs/phase2).

## Current status

The contracts, security/storage layer, F1-F5 engines, pipeline orchestration, verifier, and
fixture tooling are implemented. Unit and local integration tests pass on the available host.
Formal CIFAR-10/SVHN metrics and the 5-clean/5-poisoned ResNet-18 benchmark remain an explicit
acceptance activity because the required datasets, model artifacts, and CUDA-capable training
runtime are not present on this machine. No benchmark success claim is made in their absence.

See [`docs/IMPLEMENTATION_STATUS.md`](docs/IMPLEMENTATION_STATUS.md) for the precise evidence.

## Prerequisites

- Windows 10/11 x86-64
- Python 3.10
- Locally supplied CIFAR-10/SVHN assets, submitted model, reference models, and frozen
  ImageNet ResNet-18 extractor weights
- A 64-hex-character `SENTINEL_SECRET_KEY`
- A compatible GPU is strongly recommended for generating the formal twelve-model BadNets
  benchmark; normal assurance supports CPU execution.

## Connected staging and air-gapped installation

On a connected Windows staging machine with Python 3.10:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip download --dest wheelhouse -r requirements-build.txt -r requirements.txt
Get-FileHash wheelhouse\* -Algorithm SHA256 | Format-Table -AutoSize
```

Transfer the repository, wheelhouse, datasets, weights, and a separately reviewed hash
manifest into the air-gapped environment. Install without an index:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-index --find-links wheelhouse -r requirements-build.txt
.\.venv\Scripts\python.exe -m pip install --no-index --find-links wheelhouse -r requirements.txt
.\.venv\Scripts\python.exe -m pip install --no-index --no-build-isolation --no-deps -e .
```

Runtime code performs no model-hub or dataset downloads. Benchmark generation opens locally
present CIFAR-10 data with `download=False`.

## Input preparation

The classification manifest is JSON. Every occurrence has a unique ID and an image path
relative to the configured dataset root:

```json
{
  "dataset_id": "submitted-batch-001",
  "samples": [
    {
      "sample_id": "sample-0001",
      "image_path": "class_a/image.png",
      "label": 0,
      "source_id": "contributor-a",
      "batch_id": "batch-001"
    }
  ]
}
```

Copy `configs/default.yaml`, then set all local paths, submitted-model format and architecture,
inference sample IDs, references, extractor weights, preprocessing, and output root. The secret
is never stored in YAML or passed on the command line.

```powershell
$env:SENTINEL_SECRET_KEY = '<64 hexadecimal characters>'
.\.venv\Scripts\sentinel.exe run --config configs\default.yaml
```

Completed runs are written once to `output/runs/<report_id>/`. Interrupted work remains under
`output/staging/` and is never presented as a completed report.

## Verification

```powershell
$env:SENTINEL_SECRET_KEY = '<the verification key>'
.\.venv\Scripts\python.exe scripts\verify_run.py --run-dir output\runs\<report_id>
```

Provide `--expected-ledger-length N` when an independently retained expected length exists.
Without it, internal changes are authenticated but tail-truncation completeness is explicitly
unsupported.

## Tests and quality checks

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit tests\integration -q
.\.venv\Scripts\ruff.exe check sentinel scripts tests
.\.venv\Scripts\ruff.exe format --check sentinel scripts tests
```

Acceptance tests requiring external datasets/models are intentionally separate from the local
unit and integration suite.

## Security boundaries

Sentinel treats submitted datasets and models as untrusted, but the Phase 2 process is not a
sandbox. Safe PyTorch state-dict loading is used; arbitrary pickle model loading is excluded.
The host, operator, Sentinel code, Python runtime, configured references, verifier, and HMAC key
remain trusted. HMAC provides shared-secret integrity, not human identity or non-repudiation.
See [`SECURITY.md`](SECURITY.md) for reporting and the complete limitation summary.
