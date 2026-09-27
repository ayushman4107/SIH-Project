# Sentinel Phase 3 - Spectral Sub-Band Repair (Stretch Goal)

**Document ID:** SENTINEL-P3-SPECTRAL  
**Version:** 1.2  
**Status:** Stretch-Goal / R&D Exploration  
**Target Module:** `sentinel/modules/spectral_subband_repair.py`

## 1. Executive Summary

This document outlines the implementation plan for the Combined High-Frequency Sub-Band Isolation + Counterfactual Spectral Repair Mask feature. It is explicitly designated as a **Phase 3 Stretch Goal** because it directly contradicts the Phase 2 PRD Non-Goals (trigger discovery in submitted data). 

The module detects hard-edged, spatially-localized, and periodic anomalous patterns (e.g., checkerboards, patches) using a block-wise STFT-style frequency analysis over polar bins. To avoid phase ghosting and math artifacts, the system splits **Detection** (Spectral Domain) from **Repair** (Spatial Domain Inpainting).

## 2. Technical Architecture & Data Flow

The implementation will consist of a new class `SpectralSubbandRepairDetector` orchestrating a 3-stage pipeline:

### Stage 1: Preprocessing & Padding
1. **Channel Validation**: For BGR images, convert to **YCrCb** color space to capture both luma and isoluminant chroma triggers. For natively single-channel (grayscale) images, process the Luma equivalent only, and emit an explicit finding note that isoluminant-trigger coverage was unavailable for that sample (do not crash or silently skip).
2. **Bottom/Right Reflect Padding**: Apply reflect padding (`np.pad(..., mode='reflect')`) exclusively to the bottom and right edges to guarantee the image dimensions are perfectly divisible by the stride, preventing edge truncation without introducing artificial constant-pad discontinuities.

### Stage 2: Polar Anomaly Detection (Per-Channel)
For each processed channel (Y, Cr, Cb):
1. **Vectorized Extraction**: Extract overlapping patches using vectorized batch extraction (via `numpy.lib.stride_tricks` or similar) to avoid slow Python loops. Compute the `rfft2` in a batched manner across the patch axis.
2. Apply a Hann window to each patch before FFT.
3. Map the magnitude spectrum into a **Polar Grid** (`n_radial` × `n_angular` sectors).
4. Compute the energy fraction for every sector.
5. **Baseline Degradation Chain**: Establish the expected baseline using a strict three-tier chain:
   - **Tier 1 (Primary):** Verified-clean reference set statistics.
   - **Tier 2 (Fallback):** Within-image relative baseline (flagged `calibration_status: relative_only`).
   - **Tier 3 (Last Resort):** Dataset-wide statistics (with explicit contamination risk stated).
6. **Minimum-Sample-Size Guard**: Sectors lacking sufficient baseline samples (e.g., high-frequency corners in small reference sets) bypass scoring and report their status as `unavailable` rather than computing unstable statistics.
7. Compare each sector's fraction against the baseline using Median Absolute Deviation (MAD).
8. **Multiple-Testing Correction**: Thresholding across up to 72+ tests compounds the False Positive Rate. Note that a theoretical >50% FPR is an *illustrative upper bound* assuming statistical independence; real natural images have strong spatial/spectral correlation, making true compounding lower but still significant. Apply explicit **Benjamini-Hochberg FDR correction** to control the patch-level FPR. **Correction Family Size**: The FDR correction family must always use a fixed nominal test count (e.g., exactly `3 channels × n_radial × n_angular` tests), even if some sectors are marked `unavailable` via the minimum-sample guard. A fixed family size ensures the corrected FPR means the exact same thing across all patches and images, rather than artificially relaxing thresholds for patches with missing baseline data.
9. **Padding Overlap Penalty**: Patches whose area sits mostly inside the bottom or right reflected padding boundary receive a reduced-confidence flag, as this mirrored strip contains artificially symmetric edge structures rather than genuine organic content.
10. Flag the patch if its corrected anomaly index exceeds the configured threshold.
11. Merge flags across channels (Logical OR).

### Stage 3: Spatial Counterfactual Repair & Output
1. Construct a boolean mask by computing the **union of the full 16x16 bounding rectangles** for all flagged patch coordinates.
2. Apply **Telea fast marching inpainting** (`cv2.inpaint`) strictly on the flagged union mask using surrounding texture to hallucinate a clean counterfactual.
3. **Coordinate Clipping**: When accumulating the mask and heatmap contributions, any patch footprint extending beyond the original `(h, w)` boundary must be explicitly clipped so the resulting arrays exactly match the original dimensions. (The full repaired image is discarded as a temporary intermediate, only the heatmap is kept).
4. Compute the delta heatmap: `|original - inpainted|` inside the valid `(h, w)` region.
5. **Verdict Aggregation**: Compute a per-image verdict based on **unique flagged pixel-area as a fraction of total image area** (derived directly from the boolean mask union, inherently normalizing for overlapping stride density). 
   - **Formula**: `flagged_fraction = sum(mask) / (h * w)`
   - **Thresholds**: `flagged_fraction >= 0.005` (0.5%) yields `QUARANTINE`; `0.001 <= flagged_fraction < 0.005` yields `REVIEW`; otherwise `ACCEPT` contribution. This verdict directly feeds the existing F1 source/dataset-level chi-square concentration logic.
6. **Artifact Output & Protection Policy**: Generating a float32 `.npy` matrix for every single image creates a massive storage/I/O bloat. **Policy:** Only write `heatmap.npy` and `heatmap.png` to `artifacts/outputs/` if the image receives an adverse verdict. 
   - **Linkage**: The Finding record's `evidence.visual_artifact_ref` field stores the relative path keyed by `sample_id` (e.g., `artifacts/outputs/{sample_id}_heatmap.npy`).
   - **Protection**: This F1 artifact is NOT cryptographically bound at generation time like F3 inference records. It is protected by being digested into `run_manifest.json` at run finalization, preventing later modification. The term "protected evidence" denotes inclusion in this final manifest, not a continuous HMAC ledger chain.

## 3. Implementation Steps

### Step 1: Core Utilities & Math Formulation
- Implement `_polar_bin_masks(size, n_radial, n_angular)` to generate boolean masks for frequency sectors.
- Implement the baseline generation and the 3-tier fallback logic. Ensure minimum-sample-size guards exist for `(median, MAD)` tuples.
- Implement FDR correction (Benjamini-Hochberg) for patch-level evaluation.

### Step 2: The Detector Class
- Implement `screen_image_padded()` handling the bottom/right reflect-padding logic and grayscale fallbacks.
- Implement `screen_image_full_color()` to orchestrate the YCrCb split and logical OR combination of heatmaps and findings.
- Implement the core `_screen_single_channel()` method utilizing batched, vectorized stride-trick extraction and batched FFT.

### Step 3: Spatial Inpainting & Artifact Generation
- Implement `repair_via_spatial_inpainting()` using `cv2.inpaint` on the rectangle-union mask.
- Implement strict coordinate clipping at the `(h, w)` bounds during heatmap assembly.
- Implement the image-level verdict derivation (using the unique flagged pixel-area fraction), source-level integration rules, and conditional persistence policy.
- Update `pipeline.py` to copy the `.npy` and `.png` outputs to `artifacts/outputs/` for flagged images, ensuring their paths are deterministically keyed by `sample_id` and their digests are captured in `run_manifest.json`.

## 4. Dependencies
- **OpenCV (`cv2`)**: Required for `COLOR_BGR2YCrCb` conversion and `cv2.inpaint`.
- **NumPy & SciPy**: Standard operations, STFT, batch vectorization, and FDR statistical corrections.

## 5. Coverage Statement Additions & Limitations

If integrated into the pipeline, the `coverage_statement.json` MUST explicitly declare the following blind spots and statistical costs:
1. **FPR Compounding Risk:** Thresholding across dozens of non-independent tests artificially widens the real-world FPR. While true compounding is lower than a worst-case independent assumption, it requires Benjamini-Hochberg FDR correction and remains an unavoidable statistical cost.
2. **Inpainting Context Failure:** If a trigger occupies a massive fraction of an image, the inpainter lacks clean context and will produce a plausible but meaningless fill, breaking the counterfactual.
3. **Reference Availability:** Natively grayscale images explicitly miss isoluminant-trigger coverage.
4. **OpenCV Determinism:** `cv2.inpaint` must be empirically verified for bit-exact determinism across builds and thread configurations before relying on it for reproducible cryptographic evidence.
5. **Accepted Evasions:** 
   - Low-frequency/smooth triggers (blended color patches).
   - Spatial warping triggers (WaNet).
   - Frequency-domain camouflaged triggers (adaptive attacks).

## 6. Time, I/O, & Resource Impact
Block-wise processing scales significantly with image resolution. 
- **Compute:** Vectorized patch extraction and batched FFT processing are hard implementation requirements. Python loop-based extraction will fail the <1 hour constraint for COCO-scale runs.
- **I/O and Storage:** Persisting a float32 `.npy` heatmap artifact for every clean image would cause an unacceptable I/O bottleneck and manifest bloat. The conditional persistence policy (saving heatmaps only for flagged anomalies) is required to meet the operational budget.
