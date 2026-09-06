"""
Synthetic Transformation Projector for F4 Distribution Shift.
Analyzes the direction of OOD embeddings to determine if they align with
natural physical drift (e.g., weather, focus) or if they represent orthogonal
adversarial/synthetic manipulations.
"""
from __future__ import annotations

import torch
import torch.nn as nn
import torchvision.transforms.functional as TF


class SyntheticDriftProjector:
    def __init__(self, variance_threshold: float = 0.95, ortho_threshold: float = 0.40):
        """
        Args:
            variance_threshold: Percentage of variance to retain for the natural drift manifold.
            ortho_threshold: The ratio of orthogonal displacement (0.0 to 1.0) required to flag an attack.
        """
        self.variance_threshold = variance_threshold
        self.ortho_threshold = ortho_threshold
        
        # Manifold state variables
        self.clean_centroid = None
        self.basis_Uk = None
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    @torch.no_grad()
    def _apply_synthetic_perturbations(self, batch: torch.Tensor) -> list[torch.Tensor]:
        """Applies fast, batched tensor transformations to simulate natural physics."""
        perturbed = []
        
        # 1. Illumination Shifts (Brightness/Contrast)
        perturbed.append(TF.adjust_brightness(batch, brightness_factor=1.5))
        perturbed.append(TF.adjust_brightness(batch, brightness_factor=0.5))
        perturbed.append(TF.adjust_contrast(batch, contrast_factor=0.7))
        
        # 2. Sensor Noise (Gaussian)
        noise = torch.randn_like(batch) * 0.05
        perturbed.append(torch.clamp(batch + noise, 0, 1))
        
        # 3. Optical Blur (Gaussian Blur simulating out-of-focus)
        perturbed.append(TF.gaussian_blur(batch, kernel_size=[5, 5], sigma=[2.0, 2.0]))
        
        return perturbed

    @torch.no_grad()
    def fit_manifold(self, model: nn.Module, clean_dataloader: torch.utils.data.DataLoader):
        """
        Constructs the Natural Drift Manifold (U_k) offline using SVD on displacement covariance.
        """
        model.eval()
        model.to(self.device)
        
        clean_features = []
        perturbed_features = []
        
        for images in clean_dataloader:
            if isinstance(images, (tuple, list)):
                images = images[0]
            images = images.to(self.device)
            
            # Extract clean latent representations
            z_clean = model(images)
            clean_features.append(z_clean.cpu())
            
            # Extract perturbed latent representations
            for p_images in self._apply_synthetic_perturbations(images):
                z_pert = model(p_images)
                perturbed_features.append(z_pert.cpu())
                
        # Aggregate clean centroid
        Z_c = torch.cat(clean_features, dim=0)
        self.clean_centroid = Z_c.mean(dim=0).to(self.device)
        
        # Calculate displacement vectors: D = z_perturbed - clean_centroid
        Z_p = torch.cat(perturbed_features, dim=0).to(self.device)
        D = Z_p - self.clean_centroid
        
        # Efficient SVD via Covariance Matrix (assuming N > feature_dim)
        # Covariance C shape: (feature_dim, feature_dim)
        C = torch.cov(D.T)
        
        # Eigendecomposition (Eigenvectors are the principal components)
        eigenvalues, eigenvectors = torch.linalg.eigh(C)
        
        # Sort in descending order
        idx = torch.argsort(eigenvalues, descending=True)
        eigenvalues = eigenvalues[idx]
        eigenvectors = eigenvectors[:, idx]
        
        # Keep top k components explaining `variance_threshold`
        cumulative_variance = torch.cumsum(eigenvalues, dim=0) / (torch.sum(eigenvalues) + 1e-12)
        k = torch.searchsorted(cumulative_variance, self.variance_threshold).item() + 1
        
        # Store the basis U_k of the Natural Drift Manifold
        self.basis_Uk = eigenvectors[:, :k]
        print(f"[Projector] Manifold fitted. Feature dim: {Z_c.shape[1]} | Retained basis vectors (k): {k}")

    @torch.no_grad()
    def evaluate_batch(self, z_anomalous: torch.Tensor) -> dict[str, float | str]:
        """
        Projects an anomalous latent batch onto the natural manifold to determine disposition.
        """
        if self.basis_Uk is None or self.clean_centroid is None:
            raise RuntimeError("Projector must be fitted with `fit_manifold` prior to evaluation.")
            
        z_anomalous = z_anomalous.to(self.device)
        
        # 1. Calculate displacement from the clean centroid
        delta_z = z_anomalous.mean(dim=0) - self.clean_centroid
        
        # 2. Project onto the manifold: delta_z_parallel = U_k * (U_k^T * delta_z)
        projection_coeffs = torch.matmul(self.basis_Uk.T, delta_z)
        delta_z_parallel = torch.matmul(self.basis_Uk, projection_coeffs)
        
        # 3. Calculate the orthogonal (unnatural) residual
        delta_z_orthogonal = delta_z - delta_z_parallel
        
        # 4. Compute vector magnitudes and ratio
        norm_total = torch.norm(delta_z)
        norm_ortho = torch.norm(delta_z_orthogonal)
        
        # Handle edge case where there is virtually zero displacement
        if norm_total < 1e-6:
            ratio = 0.0
        else:
            ratio = (norm_ortho / norm_total).item()
            
        # 5. Formulate disposition
        is_attack = ratio >= self.ortho_threshold
        
        return {
            "finding_type": "ORTHOGONAL_DRIFT_ANOMALY" if is_attack else "NATURAL_COVARIATE_DRIFT",
            "orthogonality_ratio": round(ratio, 4),
            "total_displacement": round(norm_total.item(), 4),
            "disposition": "QUARANTINE" if is_attack else "REVIEW"
        }
