"""
Sybil / Distributed-Poisoning Collusion Detector — v4 (statistically validated)
================================================================================

This module catches distributed data poisoning via topological convergence in latent space.
It uses a two-stage process (Marginal-Excess binomial gate, followed by a permutation test
for cross-cluster coordination) and extracts syndicates via modularity-based community detection.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
from scipy.stats import binomtest, combine_pvalues

try:
    import hdbscan
    import umap

    _HAS_CLUSTERING_DEPS = True
except ImportError:
    _HAS_CLUSTERING_DEPS = False

import networkx as nx

logger = logging.getLogger(__name__)


def benjamini_hochberg(pvals: np.ndarray) -> np.ndarray:
    """Applies Benjamini-Hochberg FDR correction."""
    pvals = np.asarray(pvals, dtype=float)
    n = len(pvals)
    if n == 0:
        return np.array([])
    order = np.argsort(pvals)
    ranked = pvals[order]
    adj = ranked * n / np.arange(1, n + 1)
    adj = np.minimum.accumulate(adj[::-1])[::-1]
    adj = np.clip(adj, 0.0, 1.0)
    out = np.empty(n)
    out[order] = adj
    return out


def _overlap_stat(counts_i: np.ndarray, counts_j: np.ndarray) -> int:
    """Co-location mass: anomalous data landed in the exact same suspicious micro-clusters."""
    return int(np.sum(np.minimum(counts_i, counts_j)))


def cross_cluster_coordination_pvalue(
    counts_i: np.ndarray,
    counts_j: np.ndarray,
    n_perm: int = 3000,
    rng: np.random.Generator | None = None,
) -> float | None:
    """
    One-sided permutation test for Stage 2. Conditions ONLY on the pair's own
    pooled per-cluster totals to test convergence.
    """
    if rng is None:
        rng = np.random.default_rng()
    counts_i = np.asarray(counts_i, dtype=np.int64)
    counts_j = np.asarray(counts_j, dtype=np.int64)
    pooled = counts_i + counts_j
    n_i, n_j = int(counts_i.sum()), int(counts_j.sum())
    mask = pooled > 0
    pooled_nz = pooled[mask]
    if n_i == 0 or n_j == 0 or len(pooled_nz) < 2:
        return None

    observed = _overlap_stat(counts_i[mask], counts_j[mask])
    at_least_as_extreme = 0
    for _ in range(n_perm):
        draw_i = rng.multivariate_hypergeometric(pooled_nz, n_i)
        draw_j = pooled_nz - draw_i
        if _overlap_stat(draw_i, draw_j) >= observed:
            at_least_as_extreme += 1
    return (at_least_as_extreme + 1) / (n_perm + 1)


def stage1_marginal_excess_gate(
    count_matrix: np.ndarray,
    base_rates: np.ndarray,
    cluster_capacities: np.ndarray,
    alpha: float = 0.01,
):
    """
    One-sided exact binomial test per contributor per cluster.
    """
    M, K = count_matrix.shape
    raw_p = np.ones((M, K))
    for m in range(M):
        for k in range(K):
            c = int(count_matrix[m, k])
            if c == 0:
                continue
            raw_p[m, k] = binomtest(
                c, int(cluster_capacities[k]), base_rates[m], alternative="greater"
            ).pvalue
    flat = raw_p.flatten()
    nz = flat < 1.0
    adj_flat = np.ones_like(flat)
    if nz.sum() > 0:
        adj_flat[nz] = benjamini_hochberg(flat[nz])
    adj_p = adj_flat.reshape(M, K)
    return adj_p < alpha, adj_p


class SybilCollusionDetector:
    def __init__(
        self,
        min_cluster_size: int = 5,
        anomaly_percentile_cutoff: float = 95.0,
        stage1_alpha: float = 0.01,
        pairwise_fdr_alpha: float = 0.05,
        syndicate_density_threshold: float = 0.5,
        n_perm: int = 3000,
        random_state: int = 42,
    ):
        self.min_cluster_size = min_cluster_size
        self.anomaly_percentile_cutoff = anomaly_percentile_cutoff
        self.stage1_alpha = stage1_alpha
        self.pairwise_fdr_alpha = pairwise_fdr_alpha
        self.syndicate_density_threshold = syndicate_density_threshold
        self.n_perm = n_perm
        self.rng = np.random.default_rng(random_state)
        self.random_state = random_state

    def _cluster(self, latent_embeddings: np.ndarray) -> np.ndarray:
        if not _HAS_CLUSTERING_DEPS:
            raise ImportError(
                "umap-learn and hdbscan are required for the clustering "
                "front-end. Install with: pip install umap-learn hdbscan "
                "--break-system-packages"
            )
        reducer = umap.UMAP(
            n_components=10,
            n_neighbors=15,
            min_dist=0.1,
            metric="cosine",
            random_state=self.random_state,
        )
        reduced = reducer.fit_transform(latent_embeddings)
        clusterer = hdbscan.HDBSCAN(
            min_cluster_size=self.min_cluster_size,
            metric="euclidean",
        )
        return clusterer.fit_predict(reduced)

    def evaluate(
        self,
        latent_embeddings: np.ndarray,
        contributor_ids: np.ndarray,
        raw_anomaly_scores: np.ndarray,
        contributor_total_submission_counts: dict[Any, int] | None = None,
        cluster_labels: np.ndarray | None = None,
        dataset_total_samples: int | None = None,
    ) -> dict[str, Any]:
        """
        Evaluates the dataset for Sybil Collusion syndicates.
        """
        # len(latent_embeddings) if latent_embeddings is not None else len(cluster_labels)
        if cluster_labels is None:
            cluster_labels = self._cluster(latent_embeddings)

        cutoff = np.percentile(raw_anomaly_scores, self.anomaly_percentile_cutoff)
        anomalous_mask = raw_anomaly_scores >= cutoff

        suspicious_clusters = [
            c
            for c in np.unique(cluster_labels)
            if c != -1 and np.median(raw_anomaly_scores[cluster_labels == c]) >= cutoff
        ]
        if not suspicious_clusters:
            return {"status": "CLEAN", "syndicates": []}

        unique_contributors, c_idx = np.unique(contributor_ids, return_inverse=True)
        M, K = len(unique_contributors), len(suspicious_clusters)
        if M < 2:
            return {"status": "CLEAN", "reason": "SINGLE_CONTRIBUTOR"}

        count_matrix = np.zeros((M, K), dtype=np.int64)
        cluster_capacities = np.zeros(K, dtype=np.int64)
        for k, cid in enumerate(suspicious_clusters):
            in_cluster = (cluster_labels == cid) & anomalous_mask
            cluster_capacities[k] = in_cluster.sum()
            for m in range(M):
                count_matrix[m, k] = np.sum(in_cluster & (c_idx == m))

        used_uniform_prior = contributor_total_submission_counts is None
        if used_uniform_prior:
            base_rates = np.full(M, 1.0 / M)
        else:
            totals = np.array(
                [contributor_total_submission_counts.get(u, 0) for u in unique_contributors],
                dtype=float,
            )
            denom = dataset_total_samples if dataset_total_samples else totals.sum()
            if denom == 0:
                base_rates = np.full(M, 1.0 / M)
                used_uniform_prior = True
            else:
                base_rates = totals / denom

        flags, adj_p = stage1_marginal_excess_gate(
            count_matrix, base_rates, cluster_capacities, alpha=self.stage1_alpha
        )
        flagged = [m for m in range(M) if flags[m].any()]

        G = nx.Graph()
        G.add_nodes_from(unique_contributors.tolist())
        pair_records = []
        for ai, a in enumerate(flagged):
            for b in flagged[ai + 1 :]:
                shared = np.where(flags[a] & flags[b])[0]
                p_cross = cross_cluster_coordination_pvalue(
                    count_matrix[a], count_matrix[b], n_perm=self.n_perm, rng=self.rng
                )
                if len(shared) > 0:
                    p_direct = float(np.prod([adj_p[a, k] * adj_p[b, k] for k in shared]))
                    to_combine = [p_direct] + ([p_cross] if p_cross is not None else [])
                    p = (
                        combine_pvalues(to_combine, method="fisher")[1]
                        if len(to_combine) > 1
                        else p_direct
                    )
                else:
                    p = p_cross if p_cross is not None else 1.0
                pair_records.append((a, b, p))

        if not pair_records:
            return {"status": "CLEAN", "syndicates": [], "used_uniform_prior": used_uniform_prior}

        raw_p = np.array([r[2] for r in pair_records])
        adj_pair_p = benjamini_hochberg(raw_p)
        for (a, b, _), padj in zip(pair_records, adj_pair_p, strict=False):
            if padj < self.pairwise_fdr_alpha:
                G.add_edge(
                    unique_contributors[a],
                    unique_contributors[b],
                    weight=1.0 - padj,
                    adjusted_p_value=float(padj),
                )

        if G.number_of_edges() == 0:
            return {"status": "CLEAN", "syndicates": [], "used_uniform_prior": used_uniform_prior}

        syndicates = []
        for comm in nx.community.greedy_modularity_communities(G):
            if len(comm) < 2:
                continue
            sub = G.subgraph(comm)
            n = sub.number_of_nodes()
            max_edges = n * (n - 1) / 2
            density = sub.number_of_edges() / max_edges if max_edges else 0.0
            edge_ps = [d["adjusted_p_value"] for _, _, d in sub.edges(data=True)]
            min_p = min(edge_ps) if edge_ps else 1.0
            confidence = 1.0 - min_p
            if density >= self.syndicate_density_threshold and confidence >= 0.95:
                disposition = "QUARANTINE"
            elif confidence >= 0.70:
                disposition = "REVIEW"
            else:
                continue
            syndicates.append(
                {
                    "members": sorted(list(comm)),
                    "internal_edge_density": round(density, 3),
                    "calibrated_confidence": round(confidence, 4),
                    "disposition": disposition,
                }
            )

        return {
            "finding_type": "SYBIL_COLLUSION_SYNDICATE" if syndicates else "CLEAN",
            "syndicates": syndicates,
            "used_uniform_prior": used_uniform_prior,
        }
