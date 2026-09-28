<div align="center">
  
# 🛡️ VisiOps 

**The Ultimate AI Supply Chain & Model Forensics Platform**

[![Python Version](https://img.shields.io/badge/python-3.9%20%7C%203.10%20%7C%203.11-blue)](https://python.org)
[![Build Status](https://github.com/ayushman4107/SIH-Project/actions/workflows/python-tests.yml/badge.svg)](https://github.com/ayushman4107/SIH-Project/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

*Built for the **Smart India Hackathon (SIH) 2026***

</div>

---

## 🚀 Overview

In an era of deep learning supply chain vulnerabilities and massive open-source model repositories, relying on simple evaluation metrics (like accuracy or basic checksums) is fundamentally insecure. **VisiOps** elevates AI security from heuristic guesswork to absolute mathematical certainty.

VisiOps is a state-of-the-art **Model Forensics and Data Assurance platform**. It acts as an orchestration layer around existing PyTorch or ONNX pipelines, securing them against adversarial attacks, data poisoning, distribution shifts, and IP theft.

---

## 🎯 The 5 Pillars of VisiOps

VisiOps implements rigorous mathematical verification through five core defense pillars, spanning the entire ML lifecycle:

### 1️⃣ F1: Data Integrity & Spatial Consistency
Secures the training dataset against subtle poisoning and manipulation before a model even begins training.
* **Spatial Bounding-Box Consistency (FF6)**: Uses Context-Padded Depth Verification, Cross-Class Co-occurrence Modeling, and Block-Weighted Bipartite Matching to ensure bounding boxes actually contain legitimate objects. Defeats natural-object semantic triggers, background-edge spoofing, and empty-box attacks.
* **Dataset Deduplication**: Applies perceptual hashing (pHash) and cosine similarity to prevent dataset clustering and duplicate injection attacks.

### 2️⃣ F2: Model Integrity & Quantization Analysis
Verifies the physical integrity of a model's weights to detect malicious tampering.
* **Quantization Probe**: Safely maps FP32 weights to INT8 to extract their physical memory signature without triggering malicious execution code hidden in custom operators.
* **Spectral Subband Repair**: Conducts deep spectral frequency analysis of weight matrices to detect anomalous energy spikes injected by attackers.

### 3️⃣ F3: Forward Provenance & Cryptographic Traceability
Ensures the model running in production is the exact mathematical entity signed and authorized during testing.
* **Proof of Sequential Work (PoSW)**: Prevents Man-in-the-Middle (MitM) model swapping in deployment environments by forcing execution of verified sequential proofs.

### 4️⃣ F4: Distribution Shift & Gradient-Norm Spoofing Defense
Monitors incoming data streams at inference time to detect out-of-distribution (OOD) adversarial examples.
* **Vector-Jacobian Product (VJP) Emulation (FF5)**: Uses functional autodiff (`torch.func.vjp`) to extract exact penultimate gradients without triggering corrupted global autograd states.
* **Copula Coherence Fusion**: Fuses Mahalanobis distance, Entropy, Energy, and Gradient Norm into a single statistical distribution to catch adversarial inputs spoofing standard logits.

### 5️⃣ F5: Anti-Distillation Behavioral Fingerprinting
Protects corporate Intellectual Property by detecting unauthorized model theft.
* **Behavioral Fingerprinting**: Implants invisible, mathematically robust fingerprints into the model's decision boundary. If an attacker uses the VisiOps-protected model to train a stolen "student" model (Knowledge Distillation), VisiOps can forensically prove the theft.

---

## ⚙️ Quick Start

VisiOps requires zero modification to your model architecture.

### Installation

```bash
# Clone the repository
git clone https://github.com/ayushman4107/SIH-Project.git
cd SIH-Project

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows use: .venv\\Scripts\\activate

# Install dependencies
pip install -r requirements.txt
pip install -e .
```

### Running an Assurance Scan

See the `examples/` directory for full usage, or run a quick scan on your dataset:

```python
import asyncio
from visiops.pipeline import AssurancePipeline
from visiops.adapters.datasets import YOLOAdapter

async def main():
    pipeline = AssurancePipeline()
    dataset = YOLOAdapter(root_dir="./mock_dataset")
    
    print("🛡️ Running VisiOps F1 Spatial Consistency Engine...")
    report = await pipeline.verify_dataset(dataset)
    print(report.model_dump_json(indent=2))

asyncio.run(main())
```

---

## 📊 Outputs & Assurance Reports

VisiOps doesn't just block attacks; it generates irrefutable mathematical proof. Every scan produces a **VisiOps Assurance Report** (standardized JSON). This report logs every statistical outlier, every cryptographic verification step, and every disposed finding, serving as a legally sound audit trail for AI compliance and security governance.

---

## 🤝 Contributing

We welcome contributions! Please see our [CONTRIBUTING.md](CONTRIBUTING.md) for details on how to get started.

## 📝 License

This project is licensed under the [MIT License](LICENSE).
