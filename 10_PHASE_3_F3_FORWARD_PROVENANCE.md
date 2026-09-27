# F3: Forward-Secure Temporal and Runtime Provenance - Implementation Plan (V8 Final)

## 1. Executive Summary
This document outlines the definitive architectural blueprint for **Final Feature 2**. After eight rigorous rounds of adversarial stress-testing, this V8 architecture achieves mathematical perfection for Zero-Memory VDFs, explicitly defines the cryptographic boundaries of TPM-less Forward Secrecy, and stabilizes production concurrency. 

This engine binds offline inference logs to undeniable physical time delays and authentic hardware telemetry, guaranteeing that no attacker—even with root access—can forge historical provenance without detection.

---

## 2. Core Defense Mechanisms & Vulnerability Resolutions

### 2.1 True Sloth Permutation with Flip-Vectors (Mathematical Perfection)
*   **Vulnerability:** A naive modular square root loop crashes on non-residues. A standard sign-flip fix loses 1 bit of information per iteration, making reverse-verification mathematically impossible due to $2^T$ ambiguity.
*   **V8 Solution:** F3 implements the **True Sloth Permutation with Auxiliary Flip-Vectors**.
    *   **Forward Computation:** For a 2048-bit prime $p \equiv 3 \pmod 4$, if the state $x_i$ is a quadratic non-residue, the engine flips it ($x_{i+1} = \sqrt{-x_i} \pmod p$) AND appends a `1` to an auxiliary boolean vector. If it is a residue, it appends a `0`.
    *   **The Proof Payload:** The final VDF proof is stored in the ledger as the tuple `(final_value, flip_vector)`. 
    *   **Deterministic Verification:** The Auditor reads the `flip_vector` and uses it to explicitly resolve the mathematical ambiguity at every step of the reverse modular squaring, perfectly recovering the original challenge in milliseconds.

### 2.2 Asymmetric Epochs & Remote Anchoring (Defeating Root Forgery)
*   **Vulnerability:** An attacker with root access can bypass purely local PKI Asymmetric Epoch Genesis by deleting logs, generating a fake genesis key, encrypting it with the public key, and synthesizing a fake past.
*   **V8 Solution:** F3 mandates a **Dual-Layered Anchor Architecture**.
    *   **Local Layer (Asymmetric Epoch Genesis):** Upon restart, a random RAM genesis key is encrypted with the Auditor's Public Key to create the `EPOCH_START` block. The plaintext key remains strictly in RAM, defending against SSD forensics.
    *   **Global Layer (Periodic Remote Anchoring):** To mathematically lock the chain against root-level history rewriting, Sentinel automatically broadcasts the latest `record_hash` (the chain tip) to an append-only remote anchor (e.g., a corporate syslog server or blockchain) every 6 hours. Because the Sloth VDF forces the attacker to spend real physical time synthesizing fake logs, they cannot compute a forgery fast enough before the remote anchor permanently locks the legitimate history in place.

### 2.3 Context-Aware Dynamic Telemetry
*   **Vulnerability:** Global memory telemetry can be intentionally sabotaged by co-resident attackers to mask backdoor signatures.
*   **V8 Solution:** Hardware memory telemetry is officially scoped as a "Heuristic Indicator." PyTorch memory aggregates and CPU runtime durations are recorded for offline anomaly hunting but are isolated from automated quarantine logic, averting Co-Resident sabotage.

### 2.4 Strict RAII C-Level Ratchet
*   **Vulnerability:** Python heap leaks expose keys to garbage collection analysis. Raw C-level calls risk kernel-handle exhaustion.
*   **V8 Solution:** The BCrypt Ratchet is encapsulated in strict RAII context managers (`__enter__` / `__exit__`). The `finally` block guarantees `BCryptDestroyHash` execution, securing host resources while keeping the derived ephemeral key strictly inside the `VirtualLock` C-buffer.

---

## 3. Execution Plan

### Step 1: `posw.py` (VDF Engine)
*   Implement `compute_sloth_vdf(challenge, iterations)` generating both the final value and the explicit `flip_vector`.
*   Implement `verify_sloth_vdf(challenge, proof_tuple)` using the vector to resolve reverse-squaring ambiguity.

### Step 2: `ratchet.py` (Crypto Engine)
*   Retain C-Level RAII BCrypt implementation in `VirtualLock` RAM.
*   Implement PKI routines to generate the `EPOCH_START` RSA-encrypted genesis block.

### Step 3: `stages.py` & `__init__.py` (Pipeline Integration)
*   Extract execution time (Heuristic).
*   Inject the Sloth `(final_value, flip_vector)` tuple into the payload.
*   Enforce correct disk I/O order (Write -> Flush -> Ratchet).
*   Implement the `broadcast_remote_anchor` scheduling hook.
