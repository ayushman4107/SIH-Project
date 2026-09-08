"""
Robust loss functions for OPTIONAL remediation retraining only.
Never used during baseline (non-retraining) assessment.
"""

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F


class GeneralizedCrossEntropy(nn.Module):
    """
    Zhang & Sabuncu, 2018. Interpolates between MAE (fully robust, slow to
    converge) and standard CE (fast, not robust) via a single parameter q.
    q -> 0 recovers CE; q = 1 recovers MAE. q = 0.7 is the commonly-cited
    default that balances convergence speed against noise robustness.

        L_q(f(x), y) = (1 - f(x)_y^q) / q
    """

    def __init__(self, q: float = 0.7):
        super().__init__()
        assert 0 < q <= 1
        self.q = q

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        probs = F.softmax(logits, dim=1)
        p_true = probs.gather(1, targets.unsqueeze(1)).squeeze(1).clamp(min=1e-7)
        loss = (1 - p_true.pow(self.q)) / self.q
        return loss.mean()


class SymmetricCrossEntropy(nn.Module):
    """
    Wang et al., 2019. Adds a "reverse" cross-entropy term (predicted-as-true,
    true-as-predicted) to standard CE, which empirically improves robustness
    to both symmetric and asymmetric (systematic) label noise -- directly
    relevant to your "systematic mislabelling" threat model, since asymmetric
    noise is exactly what a targeted, rule-based mislabelling attack produces.

        L_sce = alpha * CE(p, y) + beta * RCE(p, y)
        RCE = reverse CE, computed by treating the PREDICTED distribution as
              the "target" and the (clamped) one-hot label as the "prediction"
    """

    def __init__(
        self,
        num_classes: int,
        alpha: float = 1.0,
        beta: float = 1.0,
        label_smoothing_floor: float = 1e-4,
    ):
        super().__init__()
        self.num_classes = num_classes
        self.alpha = alpha
        self.beta = beta
        self.floor = label_smoothing_floor

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        ce = F.cross_entropy(logits, targets)

        probs = F.softmax(logits, dim=1).clamp(min=1e-7, max=1.0)
        one_hot = F.one_hot(targets, self.num_classes).float()
        one_hot = one_hot.clamp(min=self.floor, max=1.0)  # avoid log(0) in RCE
        rce = -(probs * one_hot.log()).sum(dim=1).mean()

        return self.alpha * ce + self.beta * rce


def remediate_with_robust_loss(
    model: nn.Module,
    flagged_dataloader,  # samples flagged by any Pillar-1 detector, WITH their labels
    unflagged_dataloader,  # clean/unflagged samples from the same source
    num_classes: int,
    epochs: int = 5,
    loss_fn: nn.Module | None = None,
) -> nn.Module:
    """
    OPTIONAL remediation path. Fine-tunes only the final classification head
    (feature extractor frozen) using a robust loss, on the mixture of flagged
    and unflagged samples. This is explicitly NOT part of baseline assessment
    -- it is only invoked when an analyst chooses remediation over quarantine.
    """
    loss_fn = loss_fn or SymmetricCrossEntropy(num_classes=num_classes)
    for param in model.parameters():
        param.requires_grad = False
    for param in model.fc.parameters():  # unfreeze only the head
        param.requires_grad = True

    optimizer = torch.optim.Adam(model.fc.parameters(), lr=1e-3)
    model.train()
    for _ in range(epochs):
        for loader in (flagged_dataloader, unflagged_dataloader):
            for x, y in loader:
                optimizer.zero_grad()
                loss = loss_fn(model(x), y)
                loss.backward()
                optimizer.step()
    return model
