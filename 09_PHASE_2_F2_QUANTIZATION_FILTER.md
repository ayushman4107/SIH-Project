# F2: Quantization-Aware Divergence Filter - Implementation Plan (V7 Final)

## 1. Executive Summary
This document outlines the definitive, mathematically robust architectural blueprint for the **Quantization-Aware Divergence Filter**. Following seven exhaustive rounds of adversarial stress-testing, this V7 architecture systematically eliminates all vulnerabilities surrounding "Anomaly Shadows," "Variance Inflation Attacks," pipeline crashes, proprietary quantization mismatch, and low-sample statistical instability.

This implementation guarantees that precision drift is securely bounded across multiple deployment tiers and explicitly verifies exact deployment states, ensuring deployed models perfectly match the behavioral boundaries of the trusted reference model dynamically and at the highest granularity.

---

## 2. Core Defense Mechanisms & Vulnerability Resolutions

### 2.1 Parametric Baseline Generation (Resolving Proprietary Mismatch)
*   **Vulnerability:** Assuming F2 can natively profile all precision formats leads to mathematical mismatch if the candidate uses proprietary or advanced quantization (e.g., INT4, GPTQ, AWQ, asymmetric per-channel). Evaluating a GPTQ candidate against a generic INT8 baseline applies wildly incorrect tolerances.
*   **V7 Solution:** F2 enforces **Parametric Baseline Generation**. 
    *   The system actively interrogates the candidate's precision metadata. If the candidate utilizes a standard supported format (e.g., ONNX INT8/FP16), F2 generates the baseline natively.
    *   If the candidate utilizes a complex quantization algorithm, F2 must attempt to dynamically recompile the reference model using the exact quantization parameters provided in the candidate manifest.
    *   If generation fails, or the format is entirely proprietary, F2 gracefully degrades and reports `UNAVAILABLE` rather than executing a dangerous, mismatched integrity check.

### 2.2 Dual-Bounded Envelopes (Destroying Variance Inflation)
*   **Vulnerability:** Relying solely on Delta Z-Scores allows an attacker to execute a "Variance Inflation Attack." By intentionally injecting noise across random images, the attacker mathematically inflates the global standard deviation ($\sigma_D$) of their model's divergence. This massive denominator crushes the Z-score of their actual targeted backdoor spike, perfectly hiding it.
*   **V7 Solution:** F2 implements a mathematically airtight **Dual-Bounded Envelope**.
    1.  **Global Variance Ceiling:** We compute the candidate's divergence variance ($\sigma_D$) and mean ($\mu_D$). If $\sigma_D > \epsilon_{sigma}$ or $\mu_D > \epsilon_{mu}$, the model is immediately `QUARANTINED` for Variance Inflation.
    2.  **Absolute Hard Ceilings:** The candidate's absolute Delta on every image ($D_i$) is bounded by a strict hard ceiling. This prevents global degradation bypassing relative checks.
    3.  **Z-Score Outlier Checks:** If the model passes the first two checks, F2 evaluates the Z-score of every sample ($Z_i = \frac{D_i - \mu_D}{\sigma_D}$). If $Z_i > 5$, a targeted QAT-hidden spike is detected, triggering a `QUARANTINE`.

### 2.3 Dynamic Class-Specific Tolerances (Preventing Stable-Class Hijacking)
*   **Vulnerability:** Applying a global, static flip-rate tolerance across all classes allows attackers to safely inject targeted backdoors into ultra-stable classes up to that global limit.
*   **V7 Solution:** F2 computes **Class-Specific Tolerances ($\epsilon_c$)** dynamically. 
    *   Using the binomial confidence interval of the reference model's accuracy on each specific class, F2 assigns a near-zero tolerance to highly stable classes and mathematically proportionate allowances to naturally unstable classes.

### 2.4 Raw Logit MSE (Protecting Downstream Modules)
*   **Vulnerability:** Softmax-based metrics (JSD/Tau) are scale and shift invariant. An attacker scaling all weights by $10\times$ achieves $JSD=0.0$ but permanently collapses Predictive Entropy in downstream modules (F4).
*   **V7 Solution:** Strict enforcement of Raw Logit Mean Squared Error (MSE) constraints. Candidates must closely match the raw pre-softmax magnitude of the reference model, explicitly protecting downstream anomaly detectors.

---

## 3. Workflow & Execution Plan

### Step 1: Fit Reference (Parametric Baseline Profiling)
1.  Interrogate candidate execution parameters (format, quantization scheme).
2.  Generate the matching `target_ref` model dynamically using the provided parameters. If unsupported, return `UNAVAILABLE`.
3.  Evaluate `target_ref` alongside `ref_fp32` on the evaluation dataset.
4.  Construct `target_ref_metrics` keyed by `sample_id` and `class_id`:
    *   Per-Sample Metrics: `ref_jsd`, `ref_tau`, `ref_mse`
    *   Per-Class Metrics: `ref_smoothed_flip_rates`, binomial bounds ($\epsilon_c$).

### Step 2: Evaluate Candidate (Dual-Bounded Evaluation)
1.  **Metric Extraction:** Evaluate `candidate` against `ref_fp32` to calculate candidate degradation per sample.
2.  **ID-Mapped Pairing:** Compute paired Deltas for every sample: $D_{id} = cand\_deg_{id} - target\_ref\_deg_{id}$.
3.  **Dual-Bounded Threshold Enforcement:**
    *   Compute $\mu_D$ and $\sigma_D$ over the entire delta array.
    *   **Check 1 (Variance Inflation):** If $\sigma_D > \epsilon_{sigma}$ or $\mu_D > \epsilon_{mu} \rightarrow$ **QUARANTINE**.
    *   **Check 2 (Absolute Drift):** If $Max(D_{id}) > \epsilon_{absolute} \rightarrow$ **QUARANTINE**.
    *   **Check 3 (Z-Score Spikes):** If $Max(Z_{id}) > 5.0 \rightarrow$ **QUARANTINE**.
    *   **Check 4 (Magnitude Sabotage):** If $Max(Delta\_MSE_{id}) > \epsilon_{mse} \rightarrow$ **QUARANTINE**.
    *   **Check 5 (Targeted Class Collapse):** If any class Delta exceeds its specific $\epsilon_c \rightarrow$ **REVIEW**.
    *   Otherwise $\rightarrow$ **NORMAL_PRECISION_DRIFT**.

### Implementation Checklist
- [ ] Refactor `onnx_probe.py` > `fit_references` for parametric baseline compilation.
- [ ] Implement Dual-Bounded threshold checks (Variance ceilings, Absolute ceilings, Z-scores).
- [ ] Integrate Raw Logit MSE profiling and checks.
- [ ] Implement Dynamic Binomial Class Tolerances.
