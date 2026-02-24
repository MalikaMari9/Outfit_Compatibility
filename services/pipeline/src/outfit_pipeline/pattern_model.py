from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import torch
import torch.nn as nn
from PIL import Image
from torchvision import models, transforms


def _clip01(x: float) -> float:
    return float(max(0.0, min(1.0, x)))


@dataclass
class PatternPrediction:
    labels: List[str]
    probs: List[float]
    threshold: float
    top_label: str
    top_prob: float
    patterned: bool

    def topk(self, k: int = 3) -> List[Tuple[str, float]]:
        pairs = list(zip(self.labels, self.probs))
        pairs.sort(key=lambda x: x[1], reverse=True)
        return pairs[: max(1, int(k))]


def build_pattern_model(num_labels: int) -> nn.Module:
    model = models.resnet50(weights=None)
    model.fc = nn.Linear(model.fc.in_features, num_labels)
    return model


class PatternPredictor:
    def __init__(
        self,
        ckpt_path: str | Path,
        device: torch.device,
        threshold: Optional[float] = None,
    ) -> None:
        self.device = device
        self.ckpt_path = Path(ckpt_path)
        if not self.ckpt_path.exists():
            raise FileNotFoundError(f"Pattern checkpoint not found: {self.ckpt_path}")

        ckpt = torch.load(self.ckpt_path, map_location="cpu")
        if not isinstance(ckpt, dict):
            raise TypeError(f"Unexpected pattern checkpoint format: {type(ckpt)}")

        label_names = ckpt.get("label_names")
        if not label_names:
            raise RuntimeError(
                "Pattern checkpoint is missing 'label_names'. "
                "Use A_best_pattern_clean_colab.pt format."
            )
        self.labels = [str(x) for x in label_names]
        self.threshold = float(threshold if threshold is not None else ckpt.get("eval_thr", 0.35))
        self.img_size = int(ckpt.get("img_size", 224))

        state = ckpt.get("model_state", ckpt.get("state_dict"))
        if not isinstance(state, dict):
            raise RuntimeError("Pattern checkpoint missing model weights under 'model_state' or 'state_dict'.")

        if any(str(k).startswith("module.") for k in state.keys()):
            state = {str(k).replace("module.", "", 1): v for k, v in state.items()}

        self.model = build_pattern_model(len(self.labels))
        self.model.load_state_dict(state, strict=True)
        self.model.eval().to(self.device)

        self.tf = transforms.Compose(
            [
                transforms.Resize((self.img_size, self.img_size)),
                transforms.ToTensor(),
                transforms.Normalize(
                    mean=[0.485, 0.456, 0.406],
                    std=[0.229, 0.224, 0.225],
                ),
            ]
        )

    @torch.no_grad()
    def predict(self, img: Image.Image) -> PatternPrediction:
        x = self.tf(img).unsqueeze(0).to(self.device, non_blocking=True)
        logits = self.model(x)[0]
        probs = torch.sigmoid(logits).detach().cpu().numpy().astype(np.float32)
        top_idx = int(np.argmax(probs))
        top_label = self.labels[top_idx]
        top_prob = float(probs[top_idx])
        patterned = bool(top_prob >= self.threshold)
        return PatternPrediction(
            labels=self.labels,
            probs=probs.tolist(),
            threshold=self.threshold,
            top_label=top_label,
            top_prob=top_prob,
            patterned=patterned,
        )


_PATTERN_GROUPS = {
    "striped": "directional",
    "geometric": "directional",
    "colorblock": "directional",
    "polka_dot": "dot",
    "floral": "organic",
    "paisley": "organic",
    "nature": "organic",
    "ornate": "organic",
    "animal": "wild",
    "camo": "wild",
    "abstract": "abstract",
}


def _pattern_group(name: str) -> str:
    return _PATTERN_GROUPS.get(str(name).lower().strip(), "other")


def pattern_compat_score_from_predictions(
    top: PatternPrediction,
    bottom: PatternPrediction,
) -> float:
    t_pat = bool(top.patterned)
    b_pat = bool(bottom.patterned)

    if not t_pat and not b_pat:
        base = 0.84
    elif t_pat != b_pat:
        base = 0.90
    else:
        if top.top_label == bottom.top_label:
            base = 0.78
        elif _pattern_group(top.top_label) == _pattern_group(bottom.top_label):
            base = 0.72
        else:
            base = 0.63

    t = np.asarray(top.probs, dtype=np.float32)
    b = np.asarray(bottom.probs, dtype=np.float32)
    if t.size > 0 and b.size > 0 and t.size == b.size:
        t = t / (float(t.sum()) + 1e-8)
        b = b / (float(b.sum()) + 1e-8)
        sim = float(np.dot(t, b) / (np.linalg.norm(t) * np.linalg.norm(b) + 1e-8))
        sim = _clip01(sim)
        alpha = 0.4 if (t_pat and b_pat) else 0.2
        blended = (1.0 - alpha) * base + alpha * (0.55 + 0.45 * sim)
    else:
        blended = base

    if t_pat and b_pat:
        conf = (float(top.top_prob) + float(bottom.top_prob)) * 0.5
        blended += 0.05 * (conf - 0.5)

    return _clip01(blended)
