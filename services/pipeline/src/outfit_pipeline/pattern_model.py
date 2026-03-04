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
    raw_top_label: str = ""
    raw_top_prob: float = 0.0
    pattern_reliability: float = 1.0
    quality_score: float = 1.0
    blur_score: float = 1.0
    resolution_score: float = 1.0
    suppressed: bool = False
    suppression_reason: str = ""
    reliable: bool = True

    def topk(self, k: int = 3) -> List[Tuple[str, float]]:
        pairs = list(zip(self.labels, self.probs))
        pairs.sort(key=lambda x: x[1], reverse=True)
        return pairs[: max(1, int(k))]


def build_pattern_model(num_labels: int) -> nn.Module:
    model = models.resnet50(weights=None)
    model.fc = nn.Linear(model.fc.in_features, num_labels)
    return model


_FINE_DETAIL_LABELS = {
    "abstract",
    "floral",
    "nature",
    "ornate",
    "paisley",
    "polka_dot",
}


class PatternPredictor:
    def __init__(
        self,
        ckpt_path: str | Path,
        device: torch.device,
        threshold: Optional[float] = None,
        min_reliability: float = 0.42,
        fine_detail_guard: float = 0.58,
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
        self.min_reliability = _clip01(float(min_reliability))
        self.fine_detail_guard = _clip01(float(fine_detail_guard))
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

    def _quality_metrics(self, img: Image.Image) -> Tuple[float, float, float]:
        gray = np.asarray(img.convert("L"), dtype=np.float32)
        if gray.ndim != 2 or gray.size == 0:
            return 0.0, 0.0, 0.0

        padded = np.pad(gray, ((1, 1), (1, 1)), mode="edge")
        lap = (
            padded[:-2, 1:-1]
            + padded[2:, 1:-1]
            + padded[1:-1, :-2]
            + padded[1:-1, 2:]
            - 4.0 * padded[1:-1, 1:-1]
        )
        lap_var = float(np.var(lap))
        blur_score = _clip01((lap_var - 35.0) / 125.0)

        gx = np.abs(gray[:, 1:] - gray[:, :-1]) if gray.shape[1] > 1 else np.zeros((0,), dtype=np.float32)
        gy = np.abs(gray[1:, :] - gray[:-1, :]) if gray.shape[0] > 1 else np.zeros((0,), dtype=np.float32)
        gx_mean = float(gx.mean()) if gx.size else 0.0
        gy_mean = float(gy.mean()) if gy.size else 0.0
        edge_score = _clip01((((gx_mean + gy_mean) * 0.5) - 6.0) / 18.0)

        width, height = img.size
        min_dim = float(min(width, height))
        area = float(max(1, width * height))
        min_dim_score = _clip01((min_dim - 96.0) / 160.0)
        area_score = _clip01((area - 18000.0) / 70000.0)
        resolution_score = _clip01(0.65 * min_dim_score + 0.35 * area_score)

        quality_score = _clip01(0.55 * blur_score + 0.30 * resolution_score + 0.15 * edge_score)
        return quality_score, blur_score, resolution_score

    def _best_non_fine_detail(self, probs: np.ndarray, exclude_idx: int) -> Tuple[str, float]:
        order = np.argsort(probs)[::-1]
        for idx in order:
            if int(idx) == int(exclude_idx):
                continue
            label = str(self.labels[int(idx)])
            if label.lower().strip() in _FINE_DETAIL_LABELS:
                continue
            return label, float(probs[int(idx)])
        return "", 0.0

    def _min_reliability_for(self, label: str) -> float:
        if str(label).lower().strip() in _FINE_DETAIL_LABELS:
            return self.min_reliability
        return max(0.26, self.min_reliability - 0.08)

    @torch.no_grad()
    def predict(self, img: Image.Image) -> PatternPrediction:
        quality_score, blur_score, resolution_score = self._quality_metrics(img)
        x = self.tf(img).unsqueeze(0).to(self.device, non_blocking=True)
        logits = self.model(x)[0]
        probs = torch.sigmoid(logits).detach().cpu().numpy().astype(np.float32)
        order = np.argsort(probs)[::-1]
        top_idx = int(order[0]) if order.size else 0
        raw_top_label = self.labels[top_idx]
        raw_top_prob = float(probs[top_idx]) if probs.size else 0.0
        second_prob = float(probs[int(order[1])]) if order.size > 1 else 0.0

        margin_score = _clip01((raw_top_prob - second_prob) / 0.22)
        conf_floor = min(self.threshold, 0.30)
        confidence_score = _clip01((raw_top_prob - conf_floor) / max(1e-6, 1.0 - conf_floor))
        pattern_reliability = _clip01(
            0.50 * quality_score + 0.25 * margin_score + 0.25 * confidence_score
        )

        top_label = raw_top_label
        top_prob = raw_top_prob
        suppressed = False
        suppression_reason = ""
        if raw_top_label.lower().strip() in _FINE_DETAIL_LABELS and quality_score < self.fine_detail_guard:
            alt_label, alt_prob = self._best_non_fine_detail(probs=probs, exclude_idx=top_idx)
            suppressed = True
            if alt_label and alt_prob >= max(self.threshold, raw_top_prob * 0.60):
                top_label = alt_label
                top_prob = alt_prob
                suppression_reason = "fine_detail_low_quality_alt"
            else:
                top_label = "uncertain"
                top_prob = min(raw_top_prob, raw_top_prob * (0.45 + 0.35 * quality_score))
                suppression_reason = "fine_detail_low_quality"

        reliable = bool(
            top_label != "uncertain"
            and pattern_reliability >= self._min_reliability_for(top_label or raw_top_label)
        )
        patterned = bool(top_label != "uncertain" and top_prob >= self.threshold and reliable)
        return PatternPrediction(
            labels=self.labels,
            probs=probs.tolist(),
            threshold=self.threshold,
            top_label=top_label,
            top_prob=top_prob,
            patterned=patterned,
            raw_top_label=raw_top_label,
            raw_top_prob=raw_top_prob,
            pattern_reliability=pattern_reliability,
            quality_score=quality_score,
            blur_score=blur_score,
            resolution_score=resolution_score,
            suppressed=suppressed,
            suppression_reason=suppression_reason,
            reliable=reliable,
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
