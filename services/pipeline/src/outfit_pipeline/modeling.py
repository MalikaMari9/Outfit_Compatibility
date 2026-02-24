from __future__ import annotations

from typing import Literal

import torch
import torch.nn as nn
from torchvision import models


class PairCompatModel(nn.Module):
    def __init__(
        self,
        backbone: Literal["resnet18", "resnet50"] = "resnet18",
        embed_dim: int = 256,
        pretrained: bool = True,
        freeze_backbone: bool = True,
    ) -> None:
        super().__init__()

        if backbone == "resnet50":
            weights = models.ResNet50_Weights.DEFAULT if pretrained else None
            base = models.resnet50(weights=weights)
            in_features = base.fc.in_features
        else:
            weights = models.ResNet18_Weights.DEFAULT if pretrained else None
            base = models.resnet18(weights=weights)
            in_features = base.fc.in_features

        base.fc = nn.Identity()
        self.backbone = base

        self.embed = nn.Sequential(
            nn.Linear(in_features, embed_dim),
            nn.ReLU(inplace=True),
            nn.Dropout(0.1),
        )

        combined_dim = embed_dim * 4
        self.head = nn.Sequential(
            nn.Linear(combined_dim, 256),
            nn.ReLU(inplace=True),
            nn.Dropout(0.2),
            nn.Linear(256, 1),
        )

        if freeze_backbone:
            for p in self.backbone.parameters():
                p.requires_grad = False

    def encode(self, x: torch.Tensor) -> torch.Tensor:
        feats = self.backbone(x)
        return self.embed(feats)

    def forward(self, top: torch.Tensor, bottom: torch.Tensor) -> torch.Tensor:
        e_top = self.encode(top)
        e_bottom = self.encode(bottom)
        combined = torch.cat(
            [e_top, e_bottom, torch.abs(e_top - e_bottom), e_top * e_bottom],
            dim=1,
        )
        logits = self.head(combined)
        return logits.squeeze(1)


def load_pair_model(
    weights_path: str,
    device: torch.device,
    backbone: str = "resnet18",
    embed_dim: int = 256,
) -> PairCompatModel:
    model = PairCompatModel(
        backbone="resnet50" if backbone == "resnet50" else "resnet18",
        embed_dim=embed_dim,
        pretrained=False,
        freeze_backbone=False,
    ).to(device)

    raw = torch.load(weights_path, map_location=device)
    state = raw.get("state_dict", raw) if isinstance(raw, dict) else raw
    if not isinstance(state, dict):
        raise TypeError(f"Unsupported checkpoint format in: {weights_path}")

    # Handle DataParallel checkpoints transparently.
    if any(k.startswith("module.") for k in state.keys()):
        state = {k.replace("module.", "", 1): v for k, v in state.items()}

    model.load_state_dict(state, strict=True)
    model.eval()
    return model
