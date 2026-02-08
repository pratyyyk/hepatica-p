from __future__ import annotations

import torch
import torch.nn as nn
from torchvision.models import EfficientNet_B3_Weights, efficientnet_b3


def build_model(num_classes: int) -> nn.Module:
    model = efficientnet_b3(weights=EfficientNet_B3_Weights.IMAGENET1K_V1)
    in_features = model.classifier[-1].in_features
    model.classifier[-1] = nn.Linear(in_features, num_classes)
    return model


class TemperatureScaler(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.temperature = nn.Parameter(torch.ones(1) * 1.0)

    def forward(self, logits: torch.Tensor) -> torch.Tensor:
        temperature = torch.clamp(self.temperature, min=0.05)
        return logits / temperature


def compute_class_weights(train_targets: list[int], num_classes: int, device: torch.device) -> torch.Tensor:
    counts = torch.zeros(num_classes)
    for t in train_targets:
        counts[t] += 1
    inv = 1.0 / torch.clamp(counts, min=1.0)
    weights = inv / inv.sum() * num_classes
    return weights.to(device)
