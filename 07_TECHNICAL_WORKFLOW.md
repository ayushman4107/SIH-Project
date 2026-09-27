# Sentinel - System Technical Workflow

**Document ID:** SENTINEL-TECHNICAL-WORKFLOW  
**Version:** 1.0  
**Scope:** Phase 2 Baseline + Phase 3 Spectral Subband Integration  

This document visualizes and maps out the end-to-end technical execution of the Sentinel offline assurance pipeline.

## 1. Top-Level State Machine

The orchestration runs as a single, synchronous Python process (`pipeline.py`). To ensure cryptographic integrity and prevent partial or corrupted outputs, the system treats the output directory transactionally.

```mermaid
stateDiagram-v2
    [*] --> CLI_Invocation
    CLI_Invocation --> InputValidation
    
    InputValidation --> StagingInitialized: Config valid, paths secure
    InputValidation --> [*]: Rejected (Invalid Config/Paths)
    
    StagingInitialized --> ReferencePrep: Genesis Ledger entry created
    
    ReferencePrep --> Module_F1: ResNet-18 & Models loaded
    
    Module_F1 --> Module_F2: Data & Subband anomalies recorded
    Module_F2 --> Module_F3: Model weight integrity recorded
    
    Module_F3 --> Module_F4: Inferences bound & cryptographically signed
    Module_F4 --> Module_F5: Batch distribution shifts scored
    
    Module_F5 --> OutputFinalization: Dispositions aggregated
    
    OutputFinalization --> Run_Completed: Atomic rename to /runs/
    OutputFinalization --> FailedStaging: Schema Validation/Hash Check Failed
    
    Run_Completed --> [*]
    FailedStaging --> [*]
```

---

## 2. Component Data Flow (Pillars F1-F5)

This diagram details the sequence of mathematical and cryptographic operations that occur across the core assurance pillars.

```mermaid
flowchart TD
    subgraph Inputs [Untrusted Inputs]
        D[Classification Dataset]
        M[Submitted Model]
        C[Config YAML]
    end

    subgraph Trust [Trusted by Placement]
        R[Clean Reference Models]
        K[SENTINEL_SECRET_KEY]
        E[Frozen ResNet-18 Extractor]
    end

    subgraph F1 [F1: Data Integrity]
        F1_1(Extract Embeddings)
        F1_2(CleanLab Label Errors)
        F1_3(pHash & Cosine Duplicates)
        F1_4(Isolation Forest Outliers)
        F1_5(Phase 3: Spectral Anomaly Subband)
        
        F1_1 --> F1_2 & F1_3 & F1_4
        F1_5 -.-> |Heatmap outputs| Artifacts
    end

    subgraph F2 [F2: Model Integrity]
        F2_1(Load State Dict)
        F2_2(Extract Layer Matrices)
        F2_3(Compute SVD Spectra)
        F2_4(Wasserstein vs Clean References)
    end

    subgraph F3 [F3: Inference Provenance]
        F3_1(Forward Pass Inference)
        F3_2(Hash Input + Model + Config + Output)
        F3_3(Compute Binding HMAC-SHA256)
        F3_4(Append Authenticated Ledger Entry)
    end

    subgraph F4 [F4: Distribution Shift]
        F4_1(Ledoit-Wolf Mahalanobis OOD)
        F4_2(Predictive Entropy Ratio)
    end

    subgraph F5 [F5: Governance & Output]
        F5_1(Normalize Findings & Confidences)
        F5_2(Maximum Disposition Policy)
        F5_3(Schema Validation)
        F5_4(Atomic Directory Rename)
    end
    
    subgraph Storage [Write-Once Storage]
        Artifacts[Evidence Artifacts / .npy]
        Manifest[Run Manifest]
        Ledger[audit_log.json]
        Report[assurance_report.json]
    end

    Inputs --> F1
    E --> F1_1
    M --> F2
    R --> F2
    
    F1 --> F2 --> F3 --> F4 --> F5
    
    K --> F3_3
    F3 --> Artifacts
    F3_4 --> Ledger
    
    F5 --> Manifest
    F5 --> Report
    Manifest --> Ledger
```

---

## 3. Detailed Execution Sequence

### Phase A: Setup & Cryptographic Genesis
1. **CLI Parsing:** Sentinel is invoked without passing the secret key in the command arguments (it reads `SENTINEL_SECRET_KEY` from the environment).
2. **Path Sanitization:** Validates that no input datasets or models use path traversal escapes (`../`).
3. **Staging Creation:** Exclusively creates `output/staging/<uuid>.partial`.
4. **Ledger Genesis:** Initializes `audit_log.json`. The genesis block predecessor hash is set to 64 zeroes. 
   - *Fail-Open Rule:* If the secret key is missing, Sentinel proceeds but marks all records as `UNSIGNED` and flags the run for mandatory `REVIEW`.

### Phase B: Analysis & Feature Execution
1. **F1 Data Analysis:** 
   - Runs a 5-fold out-of-fold Logistic Regression against ResNet-18 embeddings to feed **CleanLab**.
   - Runs the **Phase 3 Spectral Subband Detector** (YCrCb, overlapping STFT, Polar Binning, Telea Inpainting). Outputs `.npy` and `.png` heatmaps only if patches are flagged.
2. **F2 Model Weights:** 
   - Slices convolution layers of the candidate model.
   - Computes Singular Value Decomposition (SVD) and compares the spectral signature against perfectly matching architecture references.
3. **F3 Inference Cryptography:**
   - Runs inferences. 
   - Hashes canonical forms of the image, the `.pt` file bytes, the config, and the `float32` output logits.
   - Computes `binding_hmac = HMAC-SHA256(key, "binding|hash1|hash2|hash3|hash4")`.
4. **F4 Distribution Shift:**
   - Compares batch-level predictive entropy against expected baseline distributions.

### Phase C: Aggregation & Finalization
1. **FDR & Thresholding:** Applies statistical normalizers (like Benjamini-Hochberg for the Spectral scanner) to control False Positive Rates.
2. **Governance Rollup:** Converts all anomalies into canonical `Finding` objects. Uses a max-severity rule (`QUARANTINE` > `REVIEW` > `ACCEPT`).
3. **Serialization:** 
   - Persists dataset evidence, heatmaps, and JSONs.
   - Builds `run_manifest.json` mapping every file to its SHA-256 digest.
4. **Final Commit:** 
   - Appends a final `run_finalized` block to the ledger, cryptographically committing to the manifest's digest. 
   - Closes, reopens, and performs a strict JSON-Schema validation on all outputs.
   - Atomically renames the folder from `staging/<id>.partial` to `runs/<id>`.
