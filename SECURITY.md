# Security Policy

## Reporting

Do not open a public issue containing secret keys, sensitive model artifacts, private datasets,
or exploitable details from a real deployment. Report the issue privately to the repository
owner with the affected commit, reproduction conditions, and sanitized evidence.

## Phase 2 threat boundary

Sentinel authenticates protected evidence against unauthorized edits by an actor who does not
possess the HMAC key and cannot replace the verifier. It does not defend against a compromised
host, process, administrator, Python runtime, Sentinel installation, verifier, or key holder.
It also does not provide asymmetric attribution, non-repudiation, trusted time, cross-session
replay prevention, or tail completeness without an independent expected ledger length.

Model files are untrusted. The safe adapter loads allowlisted architectures from state
dictionaries using `weights_only=True`. Arbitrary Python pickle model loading is intentionally
not exposed by the normal path. The single-process prototype is not a sandbox; isolate any
artifact requiring unsafe deserialization outside Sentinel.
