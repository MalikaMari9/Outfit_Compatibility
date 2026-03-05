from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

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


@dataclass(frozen=True)
class _TypeProfile:
    style: str
    volume: float
    coverage: float


_TOP_DEFAULT_PROFILE = _TypeProfile(style="casual", volume=0.48, coverage=0.45)
_BOTTOM_DEFAULT_PROFILE = _TypeProfile(style="casual", volume=0.52, coverage=0.72)

_TYPE_PROFILES = {
    "tank": _TypeProfile(style="casual", volume=0.22, coverage=0.18),
    "tee": _TypeProfile(style="casual", volume=0.34, coverage=0.28),
    "top": _TypeProfile(style="casual", volume=0.40, coverage=0.34),
    "henley": _TypeProfile(style="casual", volume=0.42, coverage=0.42),
    "halter": _TypeProfile(style="resort", volume=0.24, coverage=0.18),
    "blouse": _TypeProfile(style="smart", volume=0.42, coverage=0.44),
    "button-down": _TypeProfile(style="smart", volume=0.44, coverage=0.50),
    "turtleneck": _TypeProfile(style="smart", volume=0.46, coverage=0.60),
    "sweater": _TypeProfile(style="cozy", volume=0.56, coverage=0.60),
    "cardigan": _TypeProfile(style="cozy", volume=0.60, coverage=0.64),
    "blazer": _TypeProfile(style="tailored", volume=0.44, coverage=0.54),
    "hoodie": _TypeProfile(style="athleisure", volume=0.72, coverage=0.66),
    "flannel": _TypeProfile(style="casual", volume=0.56, coverage=0.54),
    "jersey": _TypeProfile(style="athleisure", volume=0.46, coverage=0.44),
    "bomber": _TypeProfile(style="casual_outer", volume=0.60, coverage=0.56),
    "jacket": _TypeProfile(style="outerwear", volume=0.62, coverage=0.68),
    "parka": _TypeProfile(style="outerwear", volume=0.76, coverage=0.86),
    "peacoat": _TypeProfile(style="outerwear", volume=0.62, coverage=0.82),
    "coat": _TypeProfile(style="outerwear", volume=0.68, coverage=0.88),
    "anorak": _TypeProfile(style="outerwear", volume=0.68, coverage=0.78),
    "poncho": _TypeProfile(style="statement", volume=0.86, coverage=0.72),
    "kimono": _TypeProfile(style="statement", volume=0.74, coverage=0.56),
    "coverup": _TypeProfile(style="resort", volume=0.72, coverage=0.50),
    "caftan": _TypeProfile(style="resort", volume=0.82, coverage=0.78),
    "tunic": _TypeProfile(style="smart", volume=0.60, coverage=0.56),
    "vest": _TypeProfile(style="smart", volume=0.36, coverage=0.34),
    "jeans": _TypeProfile(style="casual", volume=0.44, coverage=0.82),
    "jeggings": _TypeProfile(style="casual", volume=0.32, coverage=0.82),
    "leggings": _TypeProfile(style="athleisure", volume=0.28, coverage=0.80),
    "chinos": _TypeProfile(style="smart", volume=0.42, coverage=0.82),
    "pants": _TypeProfile(style="smart", volume=0.48, coverage=0.84),
    "jodhpurs": _TypeProfile(style="smart", volume=0.50, coverage=0.82),
    "joggers": _TypeProfile(style="athleisure", volume=0.56, coverage=0.78),
    "sweatpants": _TypeProfile(style="athleisure", volume=0.62, coverage=0.84),
    "shorts": _TypeProfile(style="casual", volume=0.42, coverage=0.28),
    "cutoffs": _TypeProfile(style="casual", volume=0.38, coverage=0.24),
    "sweatshorts": _TypeProfile(style="athleisure", volume=0.48, coverage=0.26),
    "trunks": _TypeProfile(style="resort", volume=0.44, coverage=0.22),
    "capris": _TypeProfile(style="smart", volume=0.44, coverage=0.62),
    "skirt": _TypeProfile(style="smart", volume=0.70, coverage=0.62),
    "culottes": _TypeProfile(style="smart", volume=0.78, coverage=0.62),
    "gauchos": _TypeProfile(style="statement", volume=0.82, coverage=0.64),
    "sarong": _TypeProfile(style="resort", volume=0.76, coverage=0.58),
}

_TYPE_SYNONYMS: Tuple[Tuple[str, str], ...] = (
    ("button down", "button-down"),
    ("button-down", "button-down"),
    ("long sleeve shirt", "button-down"),
    ("turtleneck sweater", "turtleneck"),
    ("male t shirt", "tee"),
    ("t shirt", "tee"),
    ("tshirt", "tee"),
    ("sleeveless top", "tank"),
    ("jacket coat", "jacket"),
    ("jacket/coat", "jacket"),
    ("trench coat", "coat"),
    ("long skirt", "skirt"),
    ("sweat shorts", "sweatshorts"),
    ("sweat pants", "sweatpants"),
    ("shirt", "top"),
    ("pant", "pants"),
)


def _normalize_label(value: str) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    for old in ("/", "_", "-", "(", ")", ","):
        text = text.replace(old, " ")
    return " ".join(text.split())


def detect_type_category(category_name: str, semantic_hint: str = "") -> str:
    label = _normalize_label(category_name)
    if not label:
        return ""

    for needle, canonical in _TYPE_SYNONYMS:
        if needle in label:
            return canonical

    for canonical in _TYPE_PROFILES:
        if canonical in label:
            return canonical

    sem = _normalize_label(semantic_hint)
    if sem == "tops":
        return "top"
    if sem == "bottoms":
        return "pants"
    return ""


def _profile_for_type(category_name: str, semantic_hint: str) -> tuple[_TypeProfile, bool]:
    canonical = detect_type_category(category_name=category_name, semantic_hint=semantic_hint)
    if canonical:
        profile = _TYPE_PROFILES.get(canonical)
        if profile is not None:
            return profile, True

    sem = _normalize_label(semantic_hint)
    if sem == "tops":
        return _TOP_DEFAULT_PROFILE, False
    if sem == "bottoms":
        return _BOTTOM_DEFAULT_PROFILE, False
    return _TypeProfile(style="casual", volume=0.50, coverage=0.58), False


def _style_pair_score(top_style: str, bottom_style: str) -> float:
    if top_style == bottom_style:
        if top_style == "statement":
            return 0.68
        return 0.86

    pair = frozenset((top_style, bottom_style))
    special = {
        frozenset(("casual", "smart")): 0.78,
        frozenset(("casual", "athleisure")): 0.84,
        frozenset(("casual", "cozy")): 0.82,
        frozenset(("smart", "tailored")): 0.92,
        frozenset(("smart", "cozy")): 0.78,
        frozenset(("smart", "statement")): 0.74,
        frozenset(("tailored", "outerwear")): 0.84,
        frozenset(("tailored", "casual")): 0.72,
        frozenset(("tailored", "resort")): 0.28,
        frozenset(("outerwear", "casual")): 0.80,
        frozenset(("outerwear", "smart")): 0.82,
        frozenset(("outerwear", "athleisure")): 0.72,
        frozenset(("outerwear", "resort")): 0.32,
        frozenset(("resort", "casual")): 0.76,
        frozenset(("resort", "smart")): 0.62,
        frozenset(("resort", "statement")): 0.72,
        frozenset(("resort", "athleisure")): 0.58,
        frozenset(("statement", "casual")): 0.72,
        frozenset(("statement", "cozy")): 0.66,
        frozenset(("casual_outer", "casual")): 0.82,
        frozenset(("casual_outer", "smart")): 0.76,
        frozenset(("casual_outer", "athleisure")): 0.78,
    }
    return special.get(pair, 0.66)


def _silhouette_balance_score(top_profile: _TypeProfile, bottom_profile: _TypeProfile) -> float:
    diff = abs(top_profile.volume - bottom_profile.volume)
    heaviness = top_profile.volume + bottom_profile.volume
    score = 0.84 - (0.14 * diff) - (0.24 * max(0.0, heaviness - 1.22))

    if top_profile.volume <= 0.40 and bottom_profile.volume >= 0.64:
        score += 0.08
    if top_profile.volume >= 0.72 and bottom_profile.volume >= 0.72:
        score -= 0.10
    if diff <= 0.16:
        score += 0.03

    return _clip01(score)


def _coverage_context_score(top_profile: _TypeProfile, bottom_profile: _TypeProfile) -> float:
    score = 0.78

    if top_profile.style in {"tailored", "outerwear"} and bottom_profile.coverage <= 0.30:
        score -= 0.28
    if top_profile.style == "outerwear" and bottom_profile.coverage <= 0.30:
        score -= 0.18
    if top_profile.style == "tailored" and bottom_profile.coverage <= 0.30:
        score -= 0.10
    if top_profile.style == "outerwear" and bottom_profile.style == "resort":
        score -= 0.24
    if top_profile.style == "tailored" and bottom_profile.style == "resort":
        score -= 0.22
    if top_profile.style in {"smart", "tailored"} and bottom_profile.coverage >= 0.60:
        score += 0.05
    if top_profile.style in {"casual", "resort"} and bottom_profile.coverage <= 0.32:
        score += 0.04
    if top_profile.style == "athleisure" and bottom_profile.style == "athleisure":
        score += 0.03

    return _clip01(score)


def _type_confidence_trust(top_confidence: float, bottom_confidence: float, recognized: float) -> float:
    confidence = min(_clip01(top_confidence), _clip01(bottom_confidence))
    return _clip01(recognized * (0.35 + (0.65 * confidence)))


def type_compatibility_score(
    top_category_name: str,
    bottom_category_name: str,
    top_semantic: str = "tops",
    bottom_semantic: str = "bottoms",
    top_confidence: float = 1.0,
    bottom_confidence: float = 1.0,
) -> float:
    top_profile, top_recognized = _profile_for_type(top_category_name, top_semantic)
    bottom_profile, bottom_recognized = _profile_for_type(bottom_category_name, bottom_semantic)

    if not top_recognized and not bottom_recognized:
        return 0.5

    style = _style_pair_score(top_profile.style, bottom_profile.style)
    silhouette = _silhouette_balance_score(top_profile, bottom_profile)
    coverage = _coverage_context_score(top_profile, bottom_profile)
    raw = _clip01((0.50 * style) + (0.35 * silhouette) + (0.15 * coverage))

    recognized_weight = 1.0 if (top_recognized and bottom_recognized) else 0.75
    trust = _type_confidence_trust(
        top_confidence=top_confidence,
        bottom_confidence=bottom_confidence,
        recognized=recognized_weight,
    )
    return _clip01(0.5 + ((raw - 0.5) * trust))


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
