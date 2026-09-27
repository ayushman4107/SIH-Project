# F4: Distribution-Shift and Anomaly Assessment - Implementation Plan

## Architectural Redesign
Following the specifications for Phase 4 (F4), the Distribution-Shift and Anomaly Assessment module will be refactored into a clear two-stage architecture:

1. **Stage 4A (Signal Extraction)**: Extracts three complementary signals from the incoming data using the preprocessed image, the admitted model, and the raw inference output.
2. **Stage 4B (Fusion and Routing)**: Fuses the three signals into a unified risk score and determines the disposition (PASS, REVIEW, or QUARANTINE).

## Stage 4A: Three Complementary Signals
We will separate the current monolithic `DistributionShiftModule` into three distinct signal generators.

### 1. Energy/Output-Level Signal
*   **Method**: `predictive_entropy_ratio` (with Temperature Scaling)
*   **Description**: Uses the predictive entropy of the softmax output to measure output-level uncertainty. To prevent overconfidence blindspots (where uncalibrated logits collapse entropy to near zero), we will apply **Temperature Scaling ($T = 1.5$)** to raw logits before computing softmax entropy.
*   **Implementation Status**: Will be refactored to apply temperature scaling and return an independent score.

### 1b. Energy-Based Score Fallback (for ONNX/Black-Box)
*   **Method**: `energy_score`
*   **Description**: A fallback signal ($E(x) = -T \cdot \\log \\sum e^{g_i(x)/T}$) used when the model is ONNX or quantized, where PyTorch autograd is unavailable for GradNorm. It guarantees three complementary signals are always maintained.

### 2. Feature-Space Signal
*   **Method**: `ledoit_wolf_mahalanobis`
*   **Description**: Measures the Mahalanobis distance of the intermediate feature embeddings relative to a reference dataset's distribution, regularized via Ledoit-Wolf shrinkage.
*   **INT8 Quantization Shift Mitigation**: To prevent false-positive quarantines from INT8 integer clipping and scaling, we will store precision-specific reference statistics (e.g., separate mean vectors and precision matrices for `fp32`, `fp16`, `int8`).
*   **Implementation Status**: Exists in `sentinel/modules/distribution_shift.py`. Will be updated for precision-awareness.

### 3. Gradient Response Signal
*   **Method**: `gradnorm_ood` (New)
*   **Description**: Implements the GradNorm OOD detection methodology (Huang et al., 2021) by computing gradients backpropagated from the Kullback-Leibler (KL) divergence between the model's softmax output and a uniform probability distribution.
*   **Implementation Constraints**:
    *   **Per-Sample Isolation**: To prevent batch-averaging bugs and memory spikes, we will use `torch.autograd.grad` with vector mapping (`torch.vmap`) explicitly isolated to the final layer weights.
    *   **Model Head Detector**: GradNorm is valid only for single-head classification. We will implement an inspection step to bypass GradNorm (falling back to Energy Score + Feature-Space) for multi-scale object detection heads (e.g., YOLO).
    *   **Format Gating**: Explicitly gated to `model_format == "pytorch"`, utilizing the Energy-Based Score fallback for ONNX/quantized assets.

## Stage 4B: Fuse and Route
Once all three signals are extracted in Stage 4A, Stage 4B will fuse them.

### Fused Risk Score
*   Each of the three signals will be normalized against their respective reference dataset thresholds.
*   **Fusion Strategy & Bonferroni Correction**: We will fuse the scores using a `max(energy_risk, feature_risk, gradient_risk)` approach. To prevent joint False Positive Rate (FPR) inflation, we will apply **Bonferroni correction** to the individual signal thresholds. If the target system FPR is $\\alpha = 0.05$, each independent signal's threshold will be tightened to $\\alpha / 3 \\approx 0.0167$. This keeps the combined `max()` fusion FPR bounded at $\\le 5\\%$.

### Routing (PASS / REVIEW / QUARANTINE)
*   **QUARANTINE**: If the fused risk score is extremely high (e.g., confidence >= 95% on the anomaly threshold), the pipeline will quarantine the output to a restricted path, blocking release.
*   **REVIEW**: If the score is elevated but below the critical threshold (e.g., confidence between 70% and 95%), it will route to an analyst queue.
*   **PASS**: If the score is well within nominal ranges, the output proceeds normally.

## Assessment Report Generation
The final output of F4 will be a structured `Assessment Report` attached to the pipeline's F4 `ModuleAssessment`. This report will contain:
1. `energy_score` (Predictive Entropy ratio)
2. `feature_distance_score` (Mahalanobis distance)
3. `gradient_signature` (GradNorm scalar)
4. `normalized_fused_risk`
5. `missing_signals` (e.g., if gradient response fails due to lack of white-box access)
6. `thresholds` (for all three metrics)
7. `recommended_action` (PASS, REVIEW, QUARANTINE)

## Execution Steps
1. **Refactor `DistributionShiftModule`**: Break `analyze()` into distinct `_extract_signals` (4A) and `_fuse_and_route` (4B) phases.
2. **Implement GradNorm**: Build the `_compute_gradnorm` logic leveraging PyTorch's autograd on the frozen model's final layer.
3. **Data Schema Update**: Update `DistributionShiftResult` (and F4's JSON schema representations) to capture the decomposed `score_components` and the `fused_risk_score`.
4. **Integration**: Update `pipeline.py` to route the preprocessed input tensors into F4 alongside the extracted embeddings and logits to support the gradient response calculation.
