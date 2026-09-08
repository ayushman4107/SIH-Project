# Sentinel Phase 2 - Product Requirements Document

**Document ID:** SENTINEL-P2-PRD  
**Version:** 1.1  
**Status:** Approved implementation baseline  
**Product stage:** Internal sub-48-hour hackathon prototype  
**Workspace:** `D:\SIH`  
**Problem statement:** SIH 26228 - Trustworthy Computer Vision Integrity Assurance for Data, Models, and Inference Outputs in Multi-Contributor Pipelines

## 1. Executive Summary

Sentinel Phase 2 is an offline, evidence-producing assurance tool for classification-oriented computer-vision pipelines. It evaluates an untrusted training dataset, an untrusted PyTorch or TorchScript model, and inference results produced during the run. It then emits a machine-readable assurance report recommending `ACCEPT`, `REVIEW`, `QUARANTINE`, or, when no assessment can be performed, `INCONCLUSIVE`.

The prototype does not attempt to prove that an asset is safe. It detects a defined set of integrity risks using reproducible heuristics and statistical methods, retains the evidence behind each adverse finding, and states where evidence is missing or a method is unavailable. Confidence values are deterministic, normalized anomaly-strength scores marked `uncalibrated`; they are not represented as true probabilities.

The product is intentionally narrower than the final SIH system. Phase 2 is a single-user, single-process Python CLI for Windows x86-64. It supports image classification, CIFAR-10-scale workloads, PyTorch and TorchScript models, HMAC-SHA256 provenance, and JSON file outputs. C++, databases, IPC, containers, dashboards, object detection, ONNX execution, asymmetric signatures, and durable replay prevention are deferred.

## 2. Product Vision and Principles

Sentinel provides a chain of evidence across five assurance pillars:

1. Inspect data for label errors, duplicate flooding, statistical outliers, and source-level concentration.
2. inspect model weights for architecture-matched spectral anomalies.
3. bind newly generated inference results to their input, model, and configuration, and verify those bindings later.
4. compare incoming data and model behavior against a declared reference distribution.
5. merge findings into a transparent, reproducible governance decision.

The governing principles are:

- **Zero implicit trust:** submitted datasets and models are untrusted. Reference assets are trusted only because the operator placed them in configured reference locations; that limitation must be reported.
- **Evidence before verdict:** every adverse finding contains its raw score, threshold, normalized confidence, affected asset, human-readable explanation, and recommended disposition.
- **Honest degradation:** an unavailable assessment is reported as `UNAVAILABLE`, never converted into a clean result.
- **No false precision:** all normalized confidence values are labeled `uncalibrated` until a statistically adequate calibration exercise exists.
- **Offline determinism:** normal execution must perform no network access or runtime downloads.
- **Non-invasive assurance:** assessment never requires retraining, fine-tuning, or otherwise modifying a submitted model. Training is performed only by the separate, team-owned synthetic benchmark generator.
- **Contributor-aware zero trust:** contributor/source identifiers are treated as attribution metadata, not as trust grants; every source is assessed by the same rules, and missing attribution is surfaced as a limitation.
- **Write-once runs:** a completed run directory is never modified by Sentinel. This is an application invariant, not filesystem-enforced immutability.

## 3. Scope

### 3.1 In Scope

- A CLI-driven, sequential assurance run on one Windows x86-64 machine.
- Classification datasets represented by an image directory plus labels and optional source/batch metadata.
- CIFAR-10 as the principal development and validation dataset.
- PyTorch `.pt` and TorchScript `.pt` classification models.
- Architecture-ready stubs for ONNX, COCO, YOLO, object detection, and segmentation that return explicit deferred-capability errors.
- Frozen ImageNet ResNet-18 embedding extraction with local weights.
- Label-error detection using CleanLab fed by five-fold out-of-fold logistic-regression probabilities.
- pHash and embedding-cosine duplicate detection.
- Isolation Forest statistical outlier detection.
- Source-level anomaly concentration and disposition.
- Per-layer SVD weight-spectrum comparison against same-architecture clean reference models.
- HMAC-SHA256 inference binding and HMAC-authenticated hash-chain entries.
- Generation and verification of provenance records.
- Ledoit-Wolf Mahalanobis OOD assessment and predictive-entropy batch shift assessment.
- A canonical JSON assurance report, audit log, coverage statement, and retained run evidence.

### 3.2 Non-Goals

- Frontend, dashboard, Figma, visualization, or desktop-shell integration.
- Production deployment or production-grade security certification.
- C/C++ modules, pybind11, local services, worker processes, IPC, UDS, shared memory, SQLite, LMDB, or content-addressable storage.
- Object-detection bounding-box assurance, segmentation, video, multimodal models, or ONNX execution.
- Black-box model fingerprinting or model assessment without loadable weights.
- Trigger discovery in submitted data, blended/physical trigger detection, adversarial-patch detection, architectural-backdoor detection, model-laundering detection, federated poisoning, or hardware compromise.
- Model remediation, pruning, unlearning, or fine-tuning of the submitted model.
- Cross-session replay detection, trusted timestamps, TPM/HSM/WORM anchoring, key rotation, key revocation, multi-user authorization, or protection from a compromised host administrator.
- A claim that an absence of findings proves safety.

## 4. Personas

### 4.1 Security Analyst

Runs an assessment, reviews evidence and limitations, and decides whether an asset should proceed. The analyst needs deterministic outputs, direct evidence references, and explicit coverage gaps rather than an opaque trust score.

### 4.2 Pipeline Operator

Prepares local datasets, submitted models, reference models, reference data, configuration, and the HMAC key. The operator needs offline installation, actionable validation errors, and predictable output locations.

### 4.3 Prototype Developer

Implements and validates detectors during a sub-48-hour sprint. The developer needs frozen contracts, deterministic seeds, separable modules, and testable acceptance criteria.

## 5. End-to-End User Outcome

Given a valid run configuration, Sentinel shall:

1. validate paths, formats, labels, metadata, reference assets, key material, and writable output location;
2. create a unique run identifier and an exclusively-created run directory;
3. calculate dataset and model digests and extract/cache embeddings;
4. execute F1-F4 sequentially, capturing findings and explicit unavailable states;
5. generate and verify protected inference records for the configured inference subset;
6. apply detector-specific confidence normalization and governance rules;
7. write artifacts to a staging directory;
8. validate every JSON artifact against its schema;
9. atomically finalize the run directory; and
10. print the report path and overall disposition.

## 6. Functional Requirements

### 6.1 F1 - Training-Data Integrity

#### PRD-F1-01: Input normalization

The product shall accept a classification dataset with stable `sample_id`, image path, integer class label, and optional `source_id` and `batch_id`. Duplicate sample identifiers, unreadable images, missing labels, out-of-range labels, or path traversal outside configured input roots shall fail validation.

COCO and YOLO adapters shall exist as callable stubs that return `CAPABILITY_DEFERRED`, not an empty dataset. `TaskType` shall include `CLASSIFICATION`, `OBJECT_DETECTION`, and `SEGMENTATION`, with only `CLASSIFICATION` executable.

#### PRD-F1-02: Frozen embeddings

The product shall load a locally supplied ImageNet ResNet-18 backbone, remove the classification head, resize images to 224x224, apply ImageNet normalization, and produce deterministic float32 embeddings. The cache key shall bind the image digest, extractor-weight digest, preprocessing configuration, and extractor version.

#### PRD-F1-03: Label-error findings

Sentinel shall use `StratifiedKFold(n_splits=5, shuffle=True, random_state=42)`. Within each fold, `StandardScaler` and class-balanced logistic regression shall be fit only on the training partition to avoid leakage. The resulting out-of-fold probabilities shall be passed to CleanLab.

For each flagged label issue:

- `raw_score` is the CleanLab label-quality score `q`;
- adverse confidence is `1 - q`;
- `decision_threshold` is the configured minimum adverse confidence;
- the evidence records provided label, most likely alternative label, both probabilities, fold identifier, and method versions.

#### PRD-F1-04: Duplicate findings

Sentinel shall calculate 64-bit pHash values and use Hamming distance <=8 as the primary visual-duplicate rule. It shall also run a complete-dataset, chunked cosine-nearest-neighbor search over embeddings with `k=10`, excluding self-matches, and flag cosine similarity >=0.95. Pairwise matches shall be collapsed into connected duplicate clusters while preserving every sample occurrence and source relationship.

#### PRD-F1-05: Statistical outliers

Sentinel shall fit an Isolation Forest to frozen embeddings using deterministic configuration. The adverse raw score is `-score_samples`. Confidence is the empirical percentile of that score within the assessed dataset and is labeled `uncalibrated`. The default finding boundary is the configured 95th percentile.

#### PRD-F1-06: Source reputation

When source metadata exists, Sentinel shall aggregate adverse sample findings per source. A chi-square concentration test may run only when at least five anomalies exist and expected cell counts are valid.

- `QUARANTINE`: `p < 0.01` and source anomaly rate is greater than twice the dataset-wide rate.
- `REVIEW`: one or more source anomalies exist but the quarantine condition is not met, including insufficient chi-square counts.
- `ACCEPT`: no anomalies are found for the source.
- Concentration status is `UNAVAILABLE` when its statistical prerequisites fail, even though the source remains `REVIEW` based on anomaly presence.

If source metadata is absent, all samples are assigned `source_id="unknown"`, and the report must state that contributor attribution was unavailable.

### 6.2 F2 - Model Integrity

#### PRD-F2-01: Format and access handling

PyTorch state-dict/full-model and TorchScript loaders shall be distinct. An unreadable or unsupported model returns an error; declared `black_box` access returns model-integrity status `UNAVAILABLE`. ONNX returns a stable deferred-capability response.

The prototype shall document that unrestricted `torch.load()` can execute pickle payloads and therefore does not safely process malicious model files. Where compatible, weights-only loading shall be preferred, but sandboxing remains out of scope.

#### PRD-F2-02: Architecture matching

A candidate model shall be compared only against reference models with the same architecture identifier and identical analyzed tensor keys/shapes. A missing or insufficient reference set returns `UNAVAILABLE`, not `BENIGN`.

#### PRD-F2-03: Per-layer spectral analysis

For every convolution weight tensor, Sentinel shall reshape weights to `[out_channels, -1]`; linear weights remain two-dimensional. Biases, normalization parameters, and tensors with fewer than two dimensions shall be excluded. Each singular-value vector shall be L1-normalized.

For each analyzed layer, the candidate spectrum shall be compared with the element-wise median spectrum from clean references using first Wasserstein distance. The model score is the 95th percentile of layer distances.

The threshold is `nextafter(max(leave_one_out_clean_scores), +infinity)`. A model score above this maximum-clean-reference threshold yields an adverse `weight_spectral_anomaly` finding. The confidence normalizer shall preserve both score and threshold and shall be documented as an uncalibrated anomaly-strength transformation.

#### PRD-F2-04: Synthetic validation protocol

Formal validation shall use five clean and five poisoned ResNet-18 models. VGG-16 shall receive one clean and one poisoned compatibility smoke test only.

- Initial seeds: 42-46; subsequent integer seeds are attempted when a run fails a quality gate.
- Poisoning: 10% of non-target training images, relabeled to target class 0.
- Trigger: RGB 3x3 checkerboard placed at `image[:, -3:, -3:]` with alternating white/black pixels beginning with white in the top-left.
- Clean-model gate: clean test accuracy >=75% and triggered target-class rate <=20% over non-target test images.
- Poisoned-model gate: clean test accuracy >=75% and ASR >=80% over triggered, non-target test images.
- Detector pass: at least 4/5 poisoned ResNet-18 models flagged and 0/5 clean ResNet-18 reference models flagged.

Rejected training runs shall retain seed, hyperparameters, accuracy, triggered target rate/ASR, failure reason, and artifact digest. Results shall be labeled demonstration-scale and shall not support generalized detection-accuracy claims.

Because the five clean models are also the threshold-calibration references, the reported `0/5` clean count is a calibration-set property, not an independent false-positive-rate estimate. The assurance report must state that limitation verbatim in substance.

### 6.3 F3 - Inference Provenance and Output Integrity

#### PRD-F3-01: Component binding

For every protected inference, Sentinel shall hash:

- original encoded input-image bytes;
- whole submitted-model file bytes;
- canonical configuration JSON; and
- the little-endian, float32, C-contiguous one-dimensional classification output vector.

`binding_hmac` shall be HMAC-SHA256 over the ASCII domain prefix `binding|` followed by the four lowercase hexadecimal digests separated by `|`.

#### PRD-F3-02: Ledger authentication and chaining

Each audit entry shall include a run-local sequence number beginning at 1, UTC timestamp, action, artifact references, binding fields where applicable, previous-entry hash, status, and disposition contribution.

`entry_hmac` shall be HMAC-SHA256 over `ledger|` followed by compact canonical JSON of every entry field except `entry_hmac`. `previous_entry_hash` shall be the SHA-256 digest of the previous compact canonical entry including its `entry_hmac`. The genesis predecessor shall be 64 lowercase zeroes.

#### PRD-F3-03: Key handling

`SENTINEL_SECRET_KEY` shall contain exactly 64 hexadecimal characters and decode to 32 bytes. Missing, malformed, or inaccessible key material shall never be logged or echoed. The same key is used for binding and ledger authentication, with domain separation.

#### PRD-F3-04: Generation and verification

Sentinel shall support both provenance generation and later verification. Verification shall re-read retained/referenced input, model, configuration, and `.npy` output; recompute all component hashes; verify the binding HMAC, entry HMAC, sequence continuity, and predecessor link; and emit field-specific failures.

#### PRD-F3-05: Fail-open exception

If provenance creation or protected audit append fails, the inference result is released with `provenance_status="UNSIGNED"`. Governance shall create a `provenance_unsigned` control finding with fixed `REVIEW`, bypassing normal confidence thresholds. The failure may be written to stderr and an explicitly unprotected diagnostic log; it must not be described as cryptographically audited.

Replay detection is limited to duplicate or reordered records within one process/run. Cross-run replay, clock rollback, restart recovery, tail truncation without an external expected length, and forgery by an attacker possessing the key are unsupported.

### 6.4 F4 - Distribution Shift

#### PRD-F4-01: OOD distance

Sentinel shall fit Ledoit-Wolf shrinkage covariance over reference embeddings and compute Mahalanobis distance for incoming samples. The default threshold is the empirical 95th percentile of reference distances. The evidence shall retain reference-set identity, covariance configuration, raw distance, percentile, and threshold.

#### PRD-F4-02: Predictive entropy ratio

The submitted model shall produce float32 logits for both the reference and incoming batches. Sentinel shall apply softmax and calculate per-sample entropy `-sum(p * log(p + epsilon))`; batch entropy is the arithmetic mean. The shift ratio is `incoming_mean / max(reference_mean, epsilon)`.

- Ratio >=1.3: `POSSIBLE_DRIFT` and `REVIEW` unless stronger evidence exists.
- Ratio <=0.7: `SUSPICIOUS` and `REVIEW` or `QUARANTINE` according to normalized anomaly confidence.
- Otherwise: `INCONCLUSIVE` shift characterization with no adverse disposition contribution.

If F2 flags the submitted model, F4 remains reportable but shall set `evidence_dependency_status="SUSPICIOUS_MODEL"`; it cannot be presented as independent corroboration.

### 6.5 F5 - Governance

#### PRD-F5-01: Canonical findings

All adverse outputs shall conform to one `Finding` contract containing: identifier, type, affected asset, severity, raw score, decision threshold, normalized confidence, calibration status, explanation, structured evidence, method/version, and recommended disposition.

#### PRD-F5-02: Disposition policy

For normalized adverse findings:

- confidence >=0.95 -> `QUARANTINE`;
- 0.70 <= confidence <0.95 -> `REVIEW`;
- confidence <0.70 -> `ACCEPT` contribution.

The overall disposition uses maximum severity: any quarantine contribution yields `QUARANTINE`; otherwise any review contribution yields `REVIEW`; otherwise `ACCEPT`. If every applicable module is unavailable, overall disposition is `INCONCLUSIVE`.

`provenance_unsigned` and source-reputation decisions are explicit policy rules and need not be derived from the generic confidence thresholds.

#### PRD-F5-03: Coverage statement

Every report shall enumerate executed checks, unavailable checks and reasons, assumptions, supported attack classes, unsupported attack classes, reference trust limitations, key-management limitations, model-loading risk, and demonstration-scale validation status.

#### PRD-F5-04: Application-level write-once output

Each run shall be written to `D:\SIH\sentinel\output\runs\<report_id>\`. Sentinel shall use exclusive creation and refuse to overwrite an existing run. Input/config/output evidence shall be copied into `artifacts/`; the model shall remain external and be referenced by path and digest. A missing model during later verification yields `UNAVAILABLE`; a present model with a different digest yields `TAMPERED`.

## 7. Security and Trust Requirements

- Normal runtime shall make no network requests.
- Reference assets are trusted by local placement; their authenticity is not verified.
- Submitted `.pt` parsing is not sandboxed and may expose pickle-deserialization risk.
- The HMAC key must never appear in reports, logs, exception messages, or command history generated by Sentinel.
- HMAC comparison shall use constant-time comparison.
- Paths shall be normalized and checked against configured roots before reads or copies.
- JSON parsers shall reject non-finite numbers where the schema requires finite numbers.
- Output finalization shall occur only after schema validation; partial work remains marked `FAILED` in staging.
- The ledger protects against unauthorized edits by actors without the key who cannot replace the verifier. It does not protect against a compromised process, key holder, host administrator, full-history rewrite with the key, or undetectable tail deletion without an independent expected length.

## 8. Product Metrics and Acceptance Criteria

| Area | Metric | Acceptance |
|---|---|---:|
| Label errors | Recall on CIFAR-10 synthetic flips at 10%, 20%, 50% | >=85% |
| Duplicates | Precision on seeded near-duplicate set | >=90% |
| Outliers | ROC AUC on declared in-/out-distribution test | >=0.75 |
| F2 poisoned models | ResNet-18 detections | >=4/5 |
| F2 clean models | ResNet-18 clean-reference flags | 0/5 calibration references; not an independent FPR estimate |
| Provenance component tampering | Detection in deterministic tests | 100% |
| Provenance internal deletion/reordering | Detection except documented tail case | 100% |
| F4 OOD | CIFAR-10 vs. SVHN ROC AUC | >=0.70 |
| Schemas | Produced artifacts valid against JSON Schema | 100% |
| Offline operation | Runtime network calls | 0 |
| Resource expectation | Peak RAM on reference machine | <8 GB, non-normative |
| Runtime expectation | Full CIFAR-10-scale run | <1 hour, non-normative |

All measured results shall include sample sizes, seeds, versions, and rejected-run metadata. A missed target shall be reported with its actual value and shall not be silently relaxed.

## 9. Deferred Capability Matrix

| Capability | Phase 2 behavior |
|---|---|
| ONNX execution | `CAPABILITY_DEFERRED` stub |
| COCO/YOLO | `CAPABILITY_DEFERRED` stub |
| Object detection/segmentation | `CAPABILITY_DEFERRED` stub |
| Black-box model integrity | `UNAVAILABLE` |
| Trigger discovery | Unsupported and declared |
| Cross-session replay | Unsupported and declared |
| Asymmetric signatures | Deferred |
| Database/IPC/services | Deferred |
| UI/RBAC | Deferred |
| C/C++ optimization | Deferred; NumPy/SciPy/PyTorch native kernels used where available |

## 10. Release Gate

Phase 2 is complete only when the five modules execute end-to-end, all required schemas validate, the audit-chain verifier detects seeded mutations, the benchmark results are recorded honestly, the offline installation succeeds from local wheels, and all known limitations appear in the generated coverage statement.
