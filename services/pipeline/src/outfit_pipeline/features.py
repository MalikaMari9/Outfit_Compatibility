from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Set

import cv2
import numpy as np


@dataclass
class Metrics:
    brightness: float
    contrast: float
    saturation: float
    colorfulness: float
    warm_pct: float


@dataclass
class ColorToken:
    name: str
    temperature: str
    hue_deg: float
    saturation: float
    value: float
    pct: float


@dataclass
class VisualFeatures:
    metrics: Metrics
    colors: List[ColorToken]
    mask_coverage: float
    effective_mask_coverage: float


def _clamp(x: float, lo: float, hi: float) -> float:
    return float(max(lo, min(hi, x)))


def _normalize_mask(mask: Optional[np.ndarray], shape: tuple[int, int]) -> np.ndarray:
    h, w = shape
    if mask is None:
        return np.ones((h, w), dtype=bool)
    m = mask.astype(np.uint8) > 0
    if m.shape != (h, w):
        raise ValueError(f"Mask shape mismatch. Expected {(h, w)} got {m.shape}")
    return m


def _refine_mask_for_visual(
    img_bgr: np.ndarray,
    mask: np.ndarray,
    ignore_low_sat_bg: bool,
    low_sat_threshold: int,
    near_white_v: int,
    near_black_v: int,
) -> np.ndarray:
    if not ignore_low_sat_bg:
        return mask
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    s = hsv[:, :, 1].astype(np.int32)
    v = hsv[:, :, 2].astype(np.int32)
    neutral_bg = (s <= int(low_sat_threshold)) & (
        (v >= int(near_white_v)) | (v <= int(near_black_v))
    )
    refined = mask & (~neutral_bg)
    # Keep refined mask only if it still has enough pixels.
    min_kept = max(80, int(0.002 * mask.size))
    if int(refined.sum()) >= min_kept:
        return refined
    return mask


def compute_metrics(img_bgr: np.ndarray, mask: Optional[np.ndarray] = None) -> Metrics:
    lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    m = _normalize_mask(mask, img_bgr.shape[:2])

    L = lab[:, :, 0].astype(np.float32)[m]
    S = hsv[:, :, 1].astype(np.float32)[m]
    H = hsv[:, :, 0].astype(np.float32)[m]

    if L.size == 0:
        return Metrics(brightness=50.0, contrast=0.0, saturation=0.0, colorfulness=0.0, warm_pct=0.0)

    brightness = float(L.mean() / 255.0 * 100.0)
    contrast = float(L.std() / 255.0 * 100.0)
    saturation = float(S.mean() / 255.0 * 100.0)

    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    R = rgb[:, :, 0].astype(np.float32)[m]
    G = rgb[:, :, 1].astype(np.float32)[m]
    B = rgb[:, :, 2].astype(np.float32)[m]
    rg = R - G
    yb = 0.5 * (R + G) - B
    colorfulness = float(np.sqrt(rg.std() ** 2 + yb.std() ** 2) + 0.3 * np.sqrt(np.abs(rg.mean()) ** 2 + np.abs(yb.mean()) ** 2))

    warm = ((H <= 25) | (H >= 160)).sum()
    warm_pct = float(warm / max(1, H.size) * 100.0)

    return Metrics(
        brightness=brightness,
        contrast=contrast,
        saturation=saturation,
        colorfulness=colorfulness,
        warm_pct=warm_pct,
    )


def color_name_from_hsv(h: float, s: float, v: float) -> tuple[str, str]:
    if v < 50:
        return "black", "neutral"
    if v > 200 and s < 30:
        return "white", "neutral"
    if s < 40:
        return "gray", "neutral"

    deg = (h / 179.0) * 360.0
    if deg < 15 or deg >= 345:
        return "red", "warm"
    if deg < 35:
        return "orange", "warm"
    if deg < 60:
        return "yellow", "warm"
    if deg < 150:
        return "green", "cool"
    if deg < 200:
        return "cyan", "cool"
    if deg < 255:
        return "blue", "cool"
    if deg < 290:
        return "purple", "cool"
    if deg < 345:
        return "pink", "warm"
    return "red", "warm"


def dominant_colors(
    img_bgr: np.ndarray,
    k: int = 3,
    mask: Optional[np.ndarray] = None,
    ignore_low_sat_bg: bool = True,
    low_sat_threshold: int = 22,
    near_white_v: int = 235,
    near_black_v: int = 20,
) -> List[ColorToken]:
    m = _normalize_mask(mask, img_bgr.shape[:2])
    pixels = img_bgr[m]
    if pixels.size == 0:
        return []

    if ignore_low_sat_bg:
        hsv = cv2.cvtColor(pixels.reshape(-1, 1, 3), cv2.COLOR_BGR2HSV).reshape(-1, 3)
        s = hsv[:, 1].astype(np.int32)
        v = hsv[:, 2].astype(np.int32)
        neutral = (s <= int(low_sat_threshold)) & (
            (v >= int(near_white_v)) | (v <= int(near_black_v))
        )
        kept = pixels[~neutral]
        if kept.shape[0] >= max(50, int(0.2 * pixels.shape[0])):
            pixels = kept

    if pixels.shape[0] > 12000:
        # Deterministic subsampling for stable scores across runs.
        idx = np.linspace(0, pixels.shape[0] - 1, num=12000, dtype=np.int64)
        pixels = pixels[idx]

    k = max(1, min(int(k), int(pixels.shape[0])))
    data = np.float32(pixels)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    _, labels, centers = cv2.kmeans(data, k, None, criteria, 5, cv2.KMEANS_PP_CENTERS)

    counts = np.bincount(labels.flatten(), minlength=k).astype(np.float32)
    total = float(counts.sum()) if counts.sum() > 0 else 1.0
    order = np.argsort(counts)[::-1]

    out: List[ColorToken] = []
    for i in order:
        b, g, r = centers[i]
        px = np.uint8([[[int(b), int(g), int(r)]]])
        hsv = cv2.cvtColor(px, cv2.COLOR_BGR2HSV)[0, 0]
        h, s, v = float(hsv[0]), float(hsv[1]), float(hsv[2])
        name, temp = color_name_from_hsv(h, s, v)
        out.append(
            ColorToken(
                name=name,
                temperature=temp,
                hue_deg=(h / 179.0) * 360.0,
                saturation=s,
                value=v,
                pct=float(counts[i] / total * 100.0),
            )
        )
    return out


def extract_visual_features(img_bgr: np.ndarray) -> VisualFeatures:
    base_mask = np.ones(img_bgr.shape[:2], dtype=bool)
    eff_mask = _refine_mask_for_visual(
        img_bgr=img_bgr,
        mask=base_mask,
        ignore_low_sat_bg=True,
        low_sat_threshold=22,
        near_white_v=235,
        near_black_v=20,
    )
    return VisualFeatures(
        metrics=compute_metrics(img_bgr, mask=eff_mask),
        colors=dominant_colors(img_bgr, k=3, mask=eff_mask),
        mask_coverage=float(base_mask.mean()),
        effective_mask_coverage=float(eff_mask.mean()),
    )


def extract_visual_features_with_mask(
    img_bgr: np.ndarray,
    mask: Optional[np.ndarray],
    ignore_low_sat_bg: bool = True,
    low_sat_threshold: int = 22,
    near_white_v: int = 235,
    near_black_v: int = 20,
) -> VisualFeatures:
    base_mask = _normalize_mask(mask, img_bgr.shape[:2])
    eff_mask = _refine_mask_for_visual(
        img_bgr=img_bgr,
        mask=base_mask,
        ignore_low_sat_bg=ignore_low_sat_bg,
        low_sat_threshold=low_sat_threshold,
        near_white_v=near_white_v,
        near_black_v=near_black_v,
    )
    return VisualFeatures(
        metrics=compute_metrics(img_bgr, mask=eff_mask),
        colors=dominant_colors(
            img_bgr,
            k=3,
            mask=eff_mask,
            ignore_low_sat_bg=ignore_low_sat_bg,
            low_sat_threshold=low_sat_threshold,
            near_white_v=near_white_v,
            near_black_v=near_black_v,
        ),
        mask_coverage=float(base_mask.mean()),
        effective_mask_coverage=float(eff_mask.mean()),
    )


def hue_distance_deg(a: float, b: float) -> float:
    d = abs(a - b)
    return min(d, 360.0 - d)


def _color_pair_harmony(a: ColorToken, b: ColorToken) -> float:
    if a.name in {"black", "white", "gray"} or b.name in {"black", "white", "gray"}:
        base = 0.82
    else:
        d = hue_distance_deg(a.hue_deg, b.hue_deg)
        if d <= 20:
            base = 0.76
        elif d <= 55:
            base = 0.90
        elif 150 <= d <= 210:
            base = 0.88
        else:
            base = 0.64

    val_diff = abs(a.value - b.value)
    if 25 <= val_diff <= 110:
        base += 0.06
    return _clamp(base, 0.0, 1.0)


def _normalized_color_weights(colors: List[ColorToken], max_colors: int = 3) -> tuple[List[ColorToken], List[float]]:
    picked = list(colors[: max(1, int(max_colors))])
    if not picked:
        return [], []

    raw = np.asarray([max(0.0, float(c.pct)) for c in picked], dtype=np.float32)
    s = float(raw.sum())
    if s <= 1e-8:
        w = np.full((len(picked),), 1.0 / len(picked), dtype=np.float32)
    else:
        w = raw / s
    return picked, [float(x) for x in w.tolist()]


def color_harmony_score(top: VisualFeatures, bottom: VisualFeatures) -> float:
    if not top.colors or not bottom.colors:
        return 0.5

    t_colors, t_weights = _normalized_color_weights(top.colors, max_colors=3)
    b_colors, b_weights = _normalized_color_weights(bottom.colors, max_colors=3)
    if not t_colors or not b_colors:
        return 0.5

    # Bidirectional best-match over top-3 palettes, weighted by cluster prevalence.
    top_to_bottom = 0.0
    for t, wt in zip(t_colors, t_weights):
        best = max(_color_pair_harmony(t, b) for b in b_colors)
        top_to_bottom += wt * best

    bottom_to_top = 0.0
    for b, wb in zip(b_colors, b_weights):
        best = max(_color_pair_harmony(t, b) for t in t_colors)
        bottom_to_top += wb * best

    bidirectional = 0.5 * (top_to_bottom + bottom_to_top)
    dominant = _color_pair_harmony(t_colors[0], b_colors[0])
    # Keep a small anchor to dominant-color behavior for backward stability.
    final = 0.85 * bidirectional + 0.15 * dominant
    return _clamp(final, 0.0, 1.0)


def brightness_compat_score(top: VisualFeatures, bottom: VisualFeatures) -> float:
    tm = top.metrics
    bm = bottom.metrics

    bdiff = abs(tm.brightness - bm.brightness)
    sdiff = abs(tm.saturation - bm.saturation)
    cdiff = abs(tm.contrast - bm.contrast)

    # Peak when brightness difference is moderate (~22), not too flat and not too extreme.
    bscore = np.exp(-((bdiff - 22.0) ** 2) / (2.0 * (20.0 ** 2)))
    sscore = np.exp(-(sdiff ** 2) / (2.0 * (30.0 ** 2)))
    cscore = np.exp(-(cdiff ** 2) / (2.0 * (20.0 ** 2)))

    out = 0.5 * float(bscore) + 0.3 * float(sscore) + 0.2 * float(cscore)
    return _clamp(out, 0.0, 1.0)


def pattern_tags(text: str) -> Set[str]:
    t = text.lower()
    tags = set()

    kws = {
        "floral": ["floral", "flower"],
        "striped": ["stripe", "striped"],
        "plaid": ["plaid", "check", "checked", "tartan"],
        "polka": ["polka", "dot"],
        "animal": ["animal", "leopard", "zebra", "snake"],
        "camo": ["camo", "camouflage"],
        "print": ["print", "printed", "patterned"],
    }

    for label, words in kws.items():
        if any(w in t for w in words):
            tags.add(label)

    if not tags:
        tags.add("solid")
    return tags


def pattern_compat_score(top_text: str, bottom_text: str) -> float:
    t = pattern_tags(top_text)
    b = pattern_tags(bottom_text)

    if t == {"solid"} and b == {"solid"}:
        return 0.84
    if ("solid" in t and len(b) > 0) or ("solid" in b and len(t) > 0):
        return 0.90
    if t & b:
        return 0.78
    return 0.63
