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
    lighting_reliability: float
    white_balance_shift: float


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


def _apply_masked_color_constancy(img_bgr: np.ndarray, mask: np.ndarray) -> tuple[np.ndarray, float]:
    m = _normalize_mask(mask, img_bgr.shape[:2])
    pixels = img_bgr[m]
    if pixels.size == 0:
        return img_bgr, 0.0

    samples_u8 = pixels.reshape(-1, 3).astype(np.uint8)
    samples = samples_u8.astype(np.float32)
    if samples.shape[0] > 16000:
        idx = np.linspace(0, samples.shape[0] - 1, num=16000, dtype=np.int64)
        samples = samples[idx]
        samples_u8 = samples_u8[idx]

    means = samples.mean(axis=0)
    means = np.maximum(means, 1.0)
    target = float(means.mean())
    raw_gains = target / means

    hsv = cv2.cvtColor(samples_u8.reshape(-1, 1, 3), cv2.COLOR_BGR2HSV).reshape(-1, 3)
    mean_sat = float(hsv[:, 1].mean()) / 255.0 if hsv.size else 0.0
    correction_strength = _clamp(1.0 - ((mean_sat - 0.18) / 0.42), 0.15, 1.0)

    gains = 1.0 + ((raw_gains - 1.0) * correction_strength)
    gains = np.clip(gains, 0.82, 1.22)

    balanced = np.clip(
        img_bgr.astype(np.float32) * gains.reshape(1, 1, 3),
        0.0,
        255.0,
    ).astype(np.uint8)
    shift = float(np.max(np.abs(gains - 1.0)))
    return balanced, shift


def _lighting_reliability(metrics: Metrics, eff_mask: np.ndarray, white_balance_shift: float) -> float:
    brightness_rel = _clamp(1.0 - abs(float(metrics.brightness) - 58.0) / 46.0, 0.10, 1.0)
    contrast_rel = _clamp(float(metrics.contrast) / 14.0, 0.15, 1.0)
    mask_rel = _clamp(float(eff_mask.mean()) / 0.10, 0.20, 1.0)
    cast_rel = _clamp(1.0 - (float(white_balance_shift) / 0.50), 0.15, 1.0)

    if float(metrics.brightness) < 14.0:
        brightness_rel *= 0.55
    elif float(metrics.brightness) > 92.0:
        brightness_rel *= 0.75

    if float(metrics.contrast) < 6.0:
        contrast_rel *= 0.70

    score = (
        0.45 * brightness_rel
        + 0.20 * contrast_rel
        + 0.15 * mask_rel
        + 0.20 * cast_rel
    )
    return _clamp(score, 0.0, 1.0)


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
    metrics = compute_metrics(img_bgr, mask=eff_mask)
    balanced_img, wb_shift = _apply_masked_color_constancy(img_bgr, eff_mask)
    lighting_rel = _lighting_reliability(metrics, eff_mask, wb_shift)
    return VisualFeatures(
        metrics=metrics,
        colors=dominant_colors(balanced_img, k=3, mask=eff_mask),
        mask_coverage=float(base_mask.mean()),
        effective_mask_coverage=float(eff_mask.mean()),
        lighting_reliability=float(lighting_rel),
        white_balance_shift=float(wb_shift),
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
    metrics = compute_metrics(img_bgr, mask=eff_mask)
    balanced_img, wb_shift = _apply_masked_color_constancy(img_bgr, eff_mask)
    lighting_rel = _lighting_reliability(metrics, eff_mask, wb_shift)
    return VisualFeatures(
        metrics=metrics,
        colors=dominant_colors(
            balanced_img,
            k=3,
            mask=eff_mask,
            ignore_low_sat_bg=ignore_low_sat_bg,
            low_sat_threshold=low_sat_threshold,
            near_white_v=near_white_v,
            near_black_v=near_black_v,
        ),
        mask_coverage=float(base_mask.mean()),
        effective_mask_coverage=float(eff_mask.mean()),
        lighting_reliability=float(lighting_rel),
        white_balance_shift=float(wb_shift),
    )


def hue_distance_deg(a: float, b: float) -> float:
    d = abs(a - b)
    return min(d, 360.0 - d)


def _colors_distinct(a: ColorToken, b: ColorToken) -> bool:
    if a.name == b.name:
        return False
    neutral_names = {"black", "white", "gray"}
    if a.name in neutral_names or b.name in neutral_names:
        return True
    return hue_distance_deg(a.hue_deg, b.hue_deg) >= 18.0


def meaningful_color_palette(colors: List[ColorToken], max_colors: int = 3) -> List[ColorToken]:
    if not colors:
        return []

    picked: List[ColorToken] = [colors[0]]
    for color in colors[1: max(1, int(max_colors))]:
        if any(not _colors_distinct(color, prev) for prev in picked):
            continue

        primary = picked[0]
        if len(picked) == 1:
            min_pct = max(16.0, float(primary.pct) * 0.35)
        else:
            min_pct = max(12.0, float(primary.pct) * 0.22)
        if float(color.pct) < min_pct:
            continue
        picked.append(color)
    return picked


def has_dual_primary(colors: List[ColorToken]) -> bool:
    return len(meaningful_color_palette(colors, max_colors=2)) >= 2


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

    top_palette = meaningful_color_palette(top.colors, max_colors=3)
    bottom_palette = meaningful_color_palette(bottom.colors, max_colors=3)

    t_colors, t_weights = _normalized_color_weights(top_palette, max_colors=3)
    b_colors, b_weights = _normalized_color_weights(bottom_palette, max_colors=3)
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
    top_is_multi = len(top_palette) >= 2
    bottom_is_multi = len(bottom_palette) >= 2
    if top_is_multi and bottom_is_multi:
        dominant_anchor = 0.05
    elif top_is_multi or bottom_is_multi:
        dominant_anchor = 0.08
    else:
        dominant_anchor = 0.15
    # Keep a small anchor to dominant-color behavior for backward stability.
    final = (1.0 - dominant_anchor) * bidirectional + dominant_anchor * dominant
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
