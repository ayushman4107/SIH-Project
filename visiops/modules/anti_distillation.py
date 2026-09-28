from __future__ import annotations
import numpy as np
import scipy.stats as stats
from scipy.optimize import linear_sum_assignment
from dataclasses import dataclass
from typing import Callable, Any

@dataclass
class FingerprintProbe:
    probe_id: str
    target_class: int
    competing_class: int
    is_peak_pocket: bool
    is_pod: bool
    tripartition_group: str  # 'HIGH', 'BUFFER', 'LOW'
    pod_dropoff_distance: float

@dataclass
class VersionedFingerprint:
    version_id: str
    probes: list[FingerprintProbe]
    class_quotas: dict[int, int]
    empirical_mahalanobis_threshold: float

class AntiDistillationEngine:
    def __init__(self, p_value_threshold: float = 0.01):
        self.p_value_threshold = p_value_threshold

    def _solve_bijective_alignment(
        self,
        confusion_matrix: np.ndarray,
        represented_classes: list[int]
    ) -> tuple[dict[int, int], float]:
        # V9 Represented-Class Sub-Alignment
        n_rep = len(represented_classes)
        if n_rep == 0:
            return {}, 1.0
            
        sub_matrix = confusion_matrix[represented_classes][:, represented_classes]
        # Hungarian algorithm minimizes cost, so we pass negative of confusion to maximize agreement
        row_ind, col_ind = linear_sum_assignment(-sub_matrix)
        
        pi = {represented_classes[r]: represented_classes[c] for r, c in zip(row_ind, col_ind)}
        trace_sum = sub_matrix[row_ind, col_ind].sum()
        
        # V9 Cross-Architecture Empirical Baselines (Simulated P-Value via trace threshold)
        expected_random = np.sum(sub_matrix) / max(1, n_rep)
        
        # Mahalanobis distance simulation: Must beat random uniformly distributed chance significantly.
        if trace_sum > expected_random * 2.5:
            p_value = 0.005 # Statistically significant alignment, rejecting competence null-hypothesis
        else:
            p_value = 0.50  # Fails empirical baseline check (independent competence)
            
        return pi, p_value

    def evaluate_candidate(
        self,
        candidate_api_fn: Callable[[np.ndarray], np.ndarray], # Returns log-probs
        probe_images: dict[str, np.ndarray],
        reference_chain: list[VersionedFingerprint]
    ) -> dict[str, Any]:
        
        best_version_match = None
        highest_global_s = 0.0
        final_disposition = "ACCEPT"
        stolen_classes = []
        
        for fingerprint in reference_chain:
            # 1. K-Repetition Querying (API wrapper expected to handle the K-averaging)
            candidate_margins = {}
            candidate_predictions = {}
            confusion_matrix = np.zeros((1000, 1000), dtype=np.float32)
            represented_classes = set()
            
            for p in fingerprint.probes:
                log_probs = candidate_api_fn(probe_images[p.probe_id])
                pred_class = int(np.argmax(log_probs))
                
                margin = log_probs[p.target_class] - log_probs[p.competing_class]
                candidate_margins[p.probe_id] = margin
                candidate_predictions[p.probe_id] = pred_class
                
                confusion_matrix[p.target_class, pred_class] += 1
                represented_classes.add(p.target_class)
                
            represented_classes = sorted(list(represented_classes))
            
            # 2. Statistically-Guarded Alignment
            pi, p_value = self._solve_bijective_alignment(confusion_matrix, represented_classes)
            
            if p_value > self.p_value_threshold:
                continue # Fails baseline check, definitively independent model
                
            # 3. Per-Class Scoring (V9 Decomposed Sub-Scores)
            class_scores = {}
            global_pred_agree = 0
            global_pred_total = 0
            global_tripartition_agree = 0
            global_tripartition_total = 0
            
            for c in represented_classes:
                class_probes = [p for p in fingerprint.probes if p.target_class == c]
                
                # S_prediction (Peak-Pocket targets under Pi)
                peak_probes = [p for p in class_probes if p.is_peak_pocket]
                pred_agree = sum(1 for p in peak_probes if candidate_predictions[p.probe_id] == pi.get(c, -1))
                
                # S_confidence (V9 Reference-Anchored Tripartitioning: Weak Monotonicity Check)
                high_probes = [p for p in class_probes if p.tripartition_group == 'HIGH']
                low_probes = [p for p in class_probes if p.tripartition_group == 'LOW']
                
                tri_agree = 0
                tri_total = len(high_probes) * len(low_probes)
                for hp in high_probes:
                    for lp in low_probes:
                        if candidate_margins[hp.probe_id] >= candidate_margins[lp.probe_id]:
                            tri_agree += 1
                            
                s_pred = pred_agree / max(1, len(peak_probes))
                s_conf = tri_agree / max(1, tri_total)
                
                s_class = 0.5 * s_pred + 0.5 * s_conf
                class_scores[c] = s_class
                
                global_pred_agree += pred_agree
                global_pred_total += len(peak_probes)
                global_tripartition_agree += tri_agree
                global_tripartition_total += tri_total
                
            global_s_pred = global_pred_agree / max(1, global_pred_total)
            global_s_conf = global_tripartition_agree / max(1, global_tripartition_total)
            global_s = 0.5 * global_s_pred + 0.5 * global_s_conf
            
            if global_s > highest_global_s:
                highest_global_s = global_s
                best_version_match = fingerprint.version_id
                
            # V9 Selective Distillation Check
            highly_similar_classes = [c for c, s in class_scores.items() if s > 0.95]
            if len(highly_similar_classes) >= 10:
                final_disposition = "QUARANTINE_SELECTIVE_DISTILLATION"
                stolen_classes = highly_similar_classes
                
            if global_s >= 0.90:
                final_disposition = "QUARANTINE_FULL_DISTILLATION"
                
        return {
            "disposition": final_disposition,
            "global_fingerprint_score": float(highest_global_s),
            "matched_version": best_version_match,
            "stolen_classes": stolen_classes
        }
