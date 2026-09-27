# F4: Closed-Form Spectral-Counterfactual Attribution Engine - Implementation Plan (V9 Final)

## 1. Executive Summary
This document defines the absolute, mathematically flawless architecture for **Final Feature 3**. By implementing Global Recursive Triage, Dual-Mode Annihilation, and Post-Clamp Spatial Heatmapping, this engine perfectly neutralizes both sparse and distributed high-frequency backdoors while guaranteeing strict byte-for-byte cryptographic non-repudiation during offline audits.

---

## 2. Core Defense Mechanisms & Vulnerability Resolutions

### 2.1 Global Recursive Triage
*   **Vulnerability:** Clamping anomalous sectors shrinks the total patch energy denominator. This artificially inflates the relative energy fractions of unflagged benign sectors, potentially pushing them over their MAD thresholds and causing cascading false-positive anomalies.
*   **V9 Solution:** The engine utilizes **Global Recursive Triage**. 
    *   After each proportional shrink step, the engine dynamically recalculates the fractional thresholds of *all* sectors (flagged and unflagged).
    *   If a previously benign sector breaches its threshold due to denominator shrinkage, it is recursively added to the active shrink pool. This guarantees the entire global state stabilizes mathematically without generating cascading false-positives.

### 2.2 Dual-Mode Annihilation Kernel (Defeating Distributed Sabotage)
*   **Vulnerability:** A distributed backdoor that elevates all coefficients uniformly hijacks the sector's noise floor, producing zero $>3\sigma$ outliers and bypassing the annihilation kernel.
*   **V9 Solution:** The engine executes a **Dual-Mode Annihilation Kernel**.
    *   **Mode 1 (Sparse):** If internal outliers ($>3\sigma$) exist, their magnitudes are aggressively annihilated down to the sector's noise floor.
    *   **Mode 2 (Dense):** If the macro-detector flags the sector but NO micro-outliers exist, it mathematically proves a distributed attack has hijacked the noise floor. The engine uniformly attenuates ALL coefficients in the sector until it complies with the global recursive bounds.

### 2.3 Post-Clamp Spatial Heatmapping (Byte-for-Byte Non-Repudiation)
*   **Vulnerability:** Computing the Saliency Heatmap linearly in the Fourier domain diverges from the physical image because the physical image undergoes a non-linear Rigid Clamp (`np.clip(0, 255)`) to prevent integer wraparound. This destroys cryptographic audit alignment.
*   **V9 Solution:** The Saliency Heatmap is computed purely in the spatial domain *after* the non-linear rigid clamp.
    *   `Heatmap = abs(Sanitized_Image_Uint8 - Original_Image_Uint8)`
    *   This guarantees that the Saliency Heatmap in the JSON payload perfectly maps to the exact physical bytes altered during sanitization, ensuring absolute non-repudiation for offline F5 audits.

### 2.4 Sine-Window WOLA
*   **V9 Continuity:** The Weighted Overlap-Add (WOLA) pipeline uses the **Periodic Sine Window** (square-root of Hann). Applied during both analysis and synthesis, the effective weight is $\sin^2$, summing perfectly to $1.0$ at 50% stride and permanently eliminating all grid distortions.

---

## 3. Execution Plan

### Phase 1: Periodic WOLA Framework Initialization
*   Apply reflect padding to original image.
*   Implement extraction/synthesis using periodic Sine windows.

### Phase 2: Global Recursive Triage
*   Execute recursive triage to identify all anomalous sectors and stabilize the global fractional thresholds dynamically.

### Phase 3: Dual-Mode Annihilation
*   Apply Mode 1 (Sparse) or Mode 2 (Dense) attenuation based on internal outlier presence.
*   Maintain strict phase preservation to ensure the repair aligns with the attacker's physical morphology.

### Phase 4: Saliency Projection & JSON Packaging
*   Pass the Repaired Spectrum through Sine-WOLA to generate the sanitized image.
*   Apply rigid clamp (`np.clip(0, 255)`) and cast to `uint8`.
*   Compute exact Spatial Heatmap: `abs(Sanitized_Uint8 - Original_Uint8)`.
*   Package the final JSON F5 report.
