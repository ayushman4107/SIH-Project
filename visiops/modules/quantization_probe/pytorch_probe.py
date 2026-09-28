from __future__ import annotations

class PyTorchQuantizationProbe:
    def fit_references(self, reference_paths, calib_dataloader, eval_dataloader):
        raise NotImplementedError("PyTorch FX quantization not implemented yet. Blocked on FX support.")

    def evaluate_candidate(self, candidate_path, reference_thresholds, calib_dataloader, eval_dataloader):
        raise NotImplementedError("PyTorch FX quantization not implemented yet. Blocked on FX support.")
