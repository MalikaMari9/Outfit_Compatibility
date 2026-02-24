from __future__ import annotations

from dataclasses import dataclass

from .config import ScoreWeights


@dataclass
class ScoreBreakdown:
    model: float
    type_prior: float
    color: float
    brightness: float
    pattern: float
    final: float


def _clip01(x: float) -> float:
    return float(max(0.0, min(1.0, x)))


def combine_scores(
    model_score: float,
    type_prior_score: float,
    color_score: float,
    brightness_score: float,
    pattern_score: float,
    weights: ScoreWeights,
) -> ScoreBreakdown:
    w = weights.normalized()

    m = _clip01(model_score)
    t = _clip01(type_prior_score)
    c = _clip01(color_score)
    b = _clip01(brightness_score)
    p = _clip01(pattern_score)

    final = (
        w.model * m
        + w.type_prior * t
        + w.color * c
        + w.brightness * b
        + w.pattern * p
    )

    return ScoreBreakdown(model=m, type_prior=t, color=c, brightness=b, pattern=p, final=_clip01(final))


def type_prior_lookup(
    top_category: str,
    bottom_category: str,
    table: dict[str, float],
    default: float = 0.5,
) -> float:
    if not top_category or not bottom_category:
        return default
    key = f"{top_category}|{bottom_category}"
    return float(table.get(key, default))


def label_from_score(
    score: float,
    threshold: float = 0.62,
    borderline_threshold: float = 0.55,
    weak_threshold: float = 0.45,
    excellent_threshold: float = 0.72,
) -> str:
    s = _clip01(score)
    good = _clip01(threshold)
    mid = _clip01(borderline_threshold)
    weak = _clip01(weak_threshold)
    excellent = _clip01(excellent_threshold)

    if excellent < good:
        excellent = good
    if good < mid:
        good = mid
    if mid < weak:
        mid = weak

    if s >= excellent:
        return "Excellent Match"
    if s >= good:
        return "Good Match"
    if s >= mid:
        return "Borderline Acceptable"
    if s >= weak:
        return "Weak Match"
    return "Mismatch"
