# 2. ARCHITECTURAL OVERVIEW & DATA FLOW

## The Unified Pipeline

This overview reflects the current state of the Sentinel CV Assurance prototype, including the newly added advanced detection modules for distributed poisoning, white-box backdoor detection, advanced drift analysis, and cryptographic key ratcheting.

```text
┌─────────────────────────────────────────────────────────────┐
│                      INPUT DATASET                           │
│     (images, labels, contributor IDs, batch metadata)        │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
        ╔═══════════════════════════════════════════╗
        ║  FEATURE 1: DATA INTEGRITY                ║
        ║  • CleanLab (Label issues)                ║
        ║  • pHash/Cosine Similarity (Duplicates)   ║
        ║  • Isolation Forest (Outliers)            ║
        ║  • Sybil Collusion Detector (Syndicates)  ║
        ║  • Influence Functions (Suspect Ranking)  ║
        ╠═══════════════════════════════════════════╣
        ║ Output: Sample-level anomalies            ║
        ║         (type, confidence, evidence)      ║
        ╚═══════════════════════════════════════════╝
                         │
                         ▼
        ╔═══════════════════════════════════════════╗
        ║  DYNAMIC REPUTATION SCORING               ║
        ║  (Aggregate to batch/source level)        ║
        ╠═══════════════════════════════════════════╣
        ║ Output: Source-level risk scores          ║
        ╚═══════════════════════════════════════════╝
                         │
         ┌───────────────┼───────────────┐
         │               │               │
         ▼               ▼               ▼
    ┌────────┐      ┌────────┐    ┌──────────┐
    │ MODELS │      │INFERENCE│    │REFERENCE │
    │(untested)(log records) │    │DISTRIBUTION
    └────────┘      └────────┘    └──────────┘
         │               │               │
         └───────────────┼───────────────┘
                         │
        ╔═══════════════════════════════════════════╗
        ║  FEATURE 2: MODEL INTEGRITY               ║
        ║  • Spectral Analysis (SVD layer weights)  ║
        ║  • Activation Clustering (ICA + k-means)  ║
        ║  • Gradient Clustering (Backdoors)        ║
        ║  • Influence Functions (Poison impact)    ║
        ╠═══════════════════════════════════════════╣
        ║ Output: Model-level screening             ║
        ║         (BENIGN/SUSPICIOUS/...)           ║
        ╚═══════════════════════════════════════════╝
                         │
        ╔═══════════════════════════════════════════╗
        ║  FEATURE 3: INFERENCE PROVENANCE          ║
        ║  • HMAC-SHA256 Input-Output Binding       ║
        ║  • HKDF Ratchet Key Security              ║
        ║  • Authenticated Audit Ledger Chaining    ║
        ╠═══════════════════════════════════════════╣
        ║ Output: Cryptographically-bound           ║
        ║         inference records & audit log     ║
        ╚═══════════════════════════════════════════╝
                         │
        ╔═══════════════════════════════════════════╗
        ║  FEATURE 4: DISTRIBUTION-SHIFT            ║
        ║  • Mahalanobis Distance OOD               ║
        ║  • Predictive Entropy Ratio               ║
        ║  • Synthetic Drift Projector (Adversarial)║
        ╠═══════════════════════════════════════════╣
        ║ Output: Sample-level OOD flags            ║
        ║         + batch-level drift report        ║
        ╚═══════════════════════════════════════════╝
                         │
        ╔═══════════════════════════════════════════╗
        ║  FEATURE 5: EVIDENCE FUSION & GOVERNANCE  ║
        ║  • Policy Enforcement & Aggregation       ║
        ║  • Maximum-severity Disposition           ║
        ║  • Coverage Statement Generation          ║
        ╠═══════════════════════════════════════════╣
        ║ Output: Assurance report JSON             ║
        ║         + coverage statement              ║
        ║         + audit trail                     ║
        ╚═══════════════════════════════════════════╝
                         │
                         ▼
            ┌──────────────────────────┐
            │  ACCEPT / REVIEW /       │
            │  QUARANTINE /            │
            │  INCONCLUSIVE DISPOSITION│
            └──────────────────────────┘
```

## Detailed Feature Breakdown

### Feature 1: Data Integrity
*   **Standard Checks:** Uses CleanLab for label errors, pHash/Cosine similarity for near-duplicates, and Isolation Forests for statistical outliers.
*   **Sybil Collusion Detector:** Analyzes contributor networks to detect distributed poisoning syndicates that attempt to evade global anomaly thresholds by splitting poisoned data.
*   **Influence Functions:** Uses gradient-based influence ranking to identify the training samples that had the most significant suspicious impact on the model.

### Feature 2: Model Integrity
*   **Spectral Analysis:** Evaluates the SVD spectra of model weights against clean references to detect large-scale parameter tampering.
*   **Activation Clustering:** Performs white-box backdoor detection by applying ICA and k-means clustering on penultimate layer activations to find bimodal (suspicious) separations.
*   **Gradient Clustering:** Complements activation clustering by analyzing gradient signatures on final-layer weights to identify backdoor triggers.

### Feature 3: Inference Provenance
*   **Cryptographic Binding:** Uses HMAC-SHA256 to bind input hashes, model digests, configuration hashes, and output predictions together.
*   **HKDF Ratchet Key Security:** Secures the signing keys using a forward-secure ratcheting scheme, protected in memory via Windows `VirtualLock` (page-locking) and `RtlSecureZeroMemory` to prevent air-gap extraction from swap files.
*   **Ledger Chaining:** Chains inference logs cryptographically to detect tampering, reordering, or tail-truncation.

### Feature 4: Distribution-Shift
*   **Mahalanobis Distance & Predictive Entropy:** Flags out-of-distribution (OOD) samples by measuring distance from the reference distribution and model uncertainty.
*   **Synthetic Drift Projector:** Distinguishes between natural covariate drift (e.g., fog, lighting changes) and adversarial/synthetic manipulation by projecting embeddings onto a natural drift manifold and measuring the orthogonal anomaly ratio.

### Feature 5: Evidence Fusion & Governance
*   Aggregates all findings across F1–F4 using a strict maximum-severity policy.
*   Produces a final disposition (`accept`, `review`, `quarantine`, `inconclusive`) alongside a comprehensive JSON assurance report and coverage statement.
