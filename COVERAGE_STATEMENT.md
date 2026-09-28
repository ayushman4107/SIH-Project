# VisiOps Coverage Statement & Limitations

This document serves as the formal coverage statement for the VisiOps Assurance Pipeline, outlining the supported attack classes, core assumptions, and known limitations of the current architecture.

## 1. Supported Attack Classes
The VisiOps pipeline is designed to detect and flag the following threat vectors across the computer-vision lifecycle:

### Data Integrity (F1)
*   **Trigger Injection (Backdoors)**: Detected via high-frequency spectral sub-band isolation and counterfactual masking.
*   **Label Flipping & Systematic Mislabelling**: Flagged via confident learning and influence function aggregation.
*   **Near-Duplicate Flooding**: Identified through perceptual hashing and cosine similarity clusters.
*   **Sybil Collusion (Contributor Level)**: Bad batches are aggregated into source-level risk scores to identify malicious contributors manipulating the dataset structure.

### Model Integrity (F2)
*   **Model Substitution / Weight Tampering**: Detected via behavioral fingerprinting across core layers (e.g., `S_Layer1`, `S_Head`).
*   **Hidden Quantization Drift**: Identified by comparing FP32 reference behavior against the INT8 candidate. Non-standard numerical drift (beyond acceptable quantization error) is flagged as anomalous.

### Inference & Distribution Shift (F3 / F4)
*   **Inference Replay / Alteration**: Prevented via the cryptographic ledger (Audit Sequence, Verifiable Delay Functions).
*   **Operational Drift vs. OOD Manipulation**: Detected using Logit Energy, Entropy, Mahalanobis Distance, and Internal Gradient Norm checks.

## 2. Core Assumptions
*   **Reference Anchors**: We assume that the baseline reference data used to compute Mahalanobis bounds (F4) and the reference FP32 model (F2) are trusted and free of backdoors prior to candidate ingestion.
*   **Cryptographic Soundness**: The integrity of the F3 ledger assumes that the private signing keys used by the preprocessing node are not compromised.
*   **Air-Gapped Operation**: The system assumes it is operating in a closed, offline environment as required by the specification. No external API calls are made.

## 3. Known Limitations (Graceful Degradation)
*   **Black-Box Constraints**: If the pipeline is only provided with black-box access to a model (e.g., APIs rather than raw PyTorch/ONNX weights), the **Internal Gradient Norm** check (F4) and **Activation Centroid** checks (F1) will gracefully fallback to "Unavailable" rather than failing the pipeline.
*   **Adversarial Adaptive Attacks**: While the spectral filter (F1) is robust to high-frequency trigger injections, sophisticated triggers encoded purely in the low-frequency domain (e.g., subtle Instagram filters) may bypass the current threshold and require manual analyst review.
*   **Retraining**: This pipeline evaluates integrity *without* retraining the contributed model. Remediation (such as unlearning a backdoor) is out of scope for the current baseline assurance pass.
