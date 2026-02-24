from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from outfit_pipeline.config import PipelineConfig
from outfit_pipeline.ollama_explainer import OllamaExplainer


def _as_float(value: object, fallback: float = 0.0) -> float:
    try:
        n = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return fallback
    if not math.isfinite(n):
        return fallback
    return n


def _as_dict(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return value
    return {}


def _to_text(value: object, fallback: str = "") -> str:
    s = str(value or "").strip()
    return s if s else fallback


def _score_label(score: float, thresholds: dict[str, object], fallback_label: str = "") -> str:
    excellent = _as_float(thresholds.get("excellent"), 0.72)
    good = _as_float(thresholds.get("good"), 0.62)
    borderline = _as_float(thresholds.get("borderline"), 0.55)
    weak = _as_float(thresholds.get("weak"), 0.45)
    if score >= excellent:
        return "Excellent Match"
    if score >= good:
        return "Good Match"
    if score >= borderline:
        return "Borderline Acceptable"
    if score >= weak:
        return "Weak Match"
    if fallback_label:
        return fallback_label
    return "Mismatch"


def _palette_relation(c1: str, c2: str) -> str:
    a = c1.lower().strip()
    b = c2.lower().strip()
    neutrals = {"black", "white", "gray", "grey", "beige", "brown", "navy", "cream"}
    if not a or not b or "unknown" in {a, b}:
        return "unknown"
    if a == b:
        return "monochrome"
    if a in neutrals or b in neutrals:
        return "neutral-anchor"
    warm = {"red", "orange", "yellow", "brown"}
    cool = {"blue", "green", "purple", "indigo", "teal"}
    if (a in warm and b in warm) or (a in cool and b in cool):
        return "analogous"
    return "contrast"


def _vibe_name(score: float, color_score: float, pattern_score: float, relation: str) -> str:
    if score >= 0.72 and relation in {"monochrome", "neutral-anchor"}:
        return "clean polished minimal"
    if score >= 0.72 and pattern_score >= 0.82:
        return "statement but controlled"
    if color_score >= 0.8 and relation == "contrast":
        return "bold color play"
    if score >= 0.62:
        return "balanced casual chic"
    if score >= 0.55:
        return "workable with tweaks"
    return "experimental mix"


def _article(word: str) -> str:
    s = word.strip().lower()
    if not s:
        return "a"
    return "an" if s[0] in {"a", "e", "i", "o", "u"} else "a"


def _fallback_explanation(facts: dict[str, object]) -> dict[str, object]:
    breakdown = _as_dict(facts.get("breakdown"))
    thresholds = _as_dict(facts.get("thresholds"))
    meta = _as_dict(facts.get("metadata"))
    score = _as_float(facts.get("final_score"), 0.0)
    label = _score_label(score, thresholds, _to_text(facts.get("label"), "Compatibility Result"))

    top_cat = _to_text(meta.get("top_category_name") or meta.get("query_category_name"), "top piece")
    bottom_cat = _to_text(meta.get("bottom_category_name") or meta.get("candidate_category_name"), "bottom piece")
    top_color = _to_text(meta.get("top_primary_color"), "unknown")
    bottom_color = _to_text(meta.get("bottom_primary_color"), "unknown")
    top_pattern = _to_text(meta.get("top_pattern_name"), "")
    bottom_pattern = _to_text(meta.get("bottom_pattern_name"), "")
    color_relation = _palette_relation(top_color, bottom_color)

    components = {
        "model compatibility": _as_float(breakdown.get("model"), 0.0),
        "type pairing": _as_float(breakdown.get("type_prior"), 0.0),
        "color harmony": _as_float(breakdown.get("color"), 0.0),
        "brightness balance": _as_float(breakdown.get("brightness"), 0.0),
        "pattern balance": _as_float(breakdown.get("pattern"), 0.0),
    }
    strongest = sorted(components.items(), key=lambda kv: kv[1], reverse=True)[:2]
    weakest = sorted(components.items(), key=lambda kv: kv[1])[:2]
    color_score = _as_float(breakdown.get("color"), 0.0)
    model_score = _as_float(breakdown.get("model"), 0.0)
    brightness_score = _as_float(breakdown.get("brightness"), 0.0)
    pattern_score = _as_float(breakdown.get("pattern"), 0.0)
    vibe = _vibe_name(score, color_score, pattern_score, color_relation)

    color_line = (
        f"The {top_color} and {bottom_color} pairing reads as {color_relation.replace('-', ' ')} and keeps visual interest."
        if color_relation != "unknown"
        else "Color relation is uncertain from the current detection, so scoring relies more on non-color signals."
    )

    why_it_works = [
        f"This pair lands at '{label}' ({score:.2f}) with a {vibe} direction.",
        color_line,
        f"Your strongest levers are {strongest[0][0]} ({strongest[0][1]:.2f}) and {strongest[1][0]} ({strongest[1][1]:.2f}).",
    ]
    if top_pattern and bottom_pattern and len(why_it_works) < 4:
        why_it_works.insert(
            2,
            f"Pattern pairing is {top_pattern.lower()} on top with {bottom_pattern.lower()} on bottom, which keeps rhythm controlled.",
        )

    risk_points: list[str] = []
    if model_score < 0.45:
        risk_points.append(
            "Silhouette chemistry is the main weak point, so the outfit can feel disconnected at full-body view."
        )
    if color_score < 0.65:
        risk_points.append("Color dialogue is less coherent, so the look may read noisy in daylight.")
    if brightness_score < 0.62:
        risk_points.append("Brightness balance is soft, which can flatten the outfit in photos.")
    if pattern_score < 0.6:
        risk_points.append("Pattern signal is weak, so texture contrast may not carry the look on its own.")
    if not risk_points:
        risk_points.append(
            f"Main pressure points are {weakest[0][0]} ({weakest[0][1]:.2f}) and {weakest[1][0]} ({weakest[1][1]:.2f}); tune those first."
        )
    risk_points = risk_points[:2]

    if color_relation == "monochrome":
        style_suggestion = (
            f"Keep the monochrome base ({top_color}) and add one sharp accent: metallic jewelry, a dark belt, or a contrasting bag."
        )
    elif color_relation == "contrast":
        style_suggestion = (
            f"Lean into the contrast with clean accessories, but keep one anchor neutral so the {top_cat.lower()} and {bottom_cat.lower()} still feel intentional."
        )
    elif model_score < 0.45:
        style_suggestion = (
            f"Keep the color story, then sharpen shape: pair this {top_cat.lower()} with a cleaner waist line or more structured {bottom_cat.lower()} cut."
        )
    elif brightness_score < 0.62:
        style_suggestion = (
            "Add a brighter or darker third piece (outer layer, shoes, or bag) to create clearer depth separation."
        )
    else:
        style_suggestion = (
            f"This is { _article(vibe) } {vibe} base. Finish with one intentional focal point (earrings, shoes, or bag) to elevate it."
        )

    confidence_note = "high" if score >= 0.72 else "medium" if score >= 0.55 else "low"

    return {
        "summary": (
            f"{top_cat.title()} with {bottom_cat.title()} reads as {vibe} and is rated {label.lower()} ({score:.2f})."
        ),
        "why_it_works": why_it_works,
        "risk_points": risk_points,
        "style_suggestion": style_suggestion,
        "confidence_note": confidence_note,
        "disclaimer": "Rule-based fallback explanation was used for this response.",
    }


def _split_clean_points(value: object, max_items: int) -> list[str]:
    if isinstance(value, list):
        raw = value
    else:
        s = str(value or "").strip()
        if not s:
            return []
        raw = [part.strip() for part in s.split(";")]
    out: list[str] = []
    for row in raw:
        s = str(row or "").strip(" -\t\r\n.")
        if not s:
            continue
        out.append(s)
        if len(out) >= max_items:
            break
    return out


def _normalize_explanation_shape(explanation: dict[str, object]) -> dict[str, object]:
    summary = _to_text(explanation.get("summary"), "")
    why = _split_clean_points(explanation.get("why_it_works"), max_items=3)
    risk = _split_clean_points(explanation.get("risk_points"), max_items=2)
    style_raw = explanation.get("style_suggestion")
    if isinstance(style_raw, list):
        style = " ".join(_split_clean_points(style_raw, max_items=3))
    else:
        style = _to_text(style_raw, "")
    confidence = _to_text(explanation.get("confidence_note"), "medium").lower()
    if confidence not in {"high", "medium", "low"}:
        confidence = "medium"
    return {
        "summary": summary,
        "why_it_works": why,
        "risk_points": risk,
        "style_suggestion": style,
        "confidence_note": confidence,
        "disclaimer": _to_text(explanation.get("disclaimer"), "Explanation only; score and label are unchanged."),
    }


def _component_phrase(kind: str, strong: bool) -> str:
    if kind == "model":
        return (
            "The silhouette connection is clean, so the outfit reads intentional as one look."
            if strong
            else "The silhouette link is the weak point right now, so the outfit can feel disconnected head-to-toe."
        )
    if kind == "type_prior":
        return (
            "The garment pairing feels naturally wearable, which makes styling easier."
            if strong
            else "This top/bottom pairing is less intuitive, so it needs stronger styling anchors."
        )
    if kind == "color":
        return (
            "The color pairing is coherent and easy on the eye."
            if strong
            else "Color harmony is the friction point, so the look may feel off in natural light."
        )
    if kind == "brightness":
        return (
            "Lightness contrast is balanced, giving the outfit depth without harsh contrast."
            if strong
            else "Brightness balance is soft, so the outfit can look flatter in photos."
        )
    if kind == "pattern":
        return (
            "Pattern/texture balance adds interest without getting noisy."
            if strong
            else "Pattern energy is low, so the look can feel plain unless texture is added elsewhere."
        )
    return "The outfit signal is balanced."


def _rank_components(breakdown: dict[str, object]) -> list[tuple[str, float]]:
    slots = [
        ("model", _as_float(breakdown.get("model"), 0.0)),
        ("type_prior", _as_float(breakdown.get("type_prior"), 0.0)),
        ("color", _as_float(breakdown.get("color"), 0.0)),
        ("brightness", _as_float(breakdown.get("brightness"), 0.0)),
        ("pattern", _as_float(breakdown.get("pattern"), 0.0)),
    ]
    return sorted(slots, key=lambda kv: kv[1], reverse=True)


def _compose_human_rewrite(facts: dict[str, object], current: dict[str, object]) -> dict[str, object]:
    breakdown = _as_dict(facts.get("breakdown"))
    thresholds = _as_dict(facts.get("thresholds"))
    meta = _as_dict(facts.get("metadata"))
    score = _as_float(facts.get("final_score"), 0.0)
    label = _score_label(score, thresholds, _to_text(facts.get("label"), "Compatibility Result"))
    top_cat = _to_text(meta.get("top_category_name") or meta.get("query_category_name"), "top piece").title()
    bottom_cat = _to_text(meta.get("bottom_category_name") or meta.get("candidate_category_name"), "bottom piece").title()
    top_color = _to_text(meta.get("top_primary_color"), "unknown").lower()
    bottom_color = _to_text(meta.get("bottom_primary_color"), "unknown").lower()
    top_pattern = _to_text(meta.get("top_pattern_name"), "").lower()
    bottom_pattern = _to_text(meta.get("bottom_pattern_name"), "").lower()
    relation = _palette_relation(top_color, bottom_color)

    ranked = _rank_components(breakdown)
    strongest = ranked[:2]
    weakest = ranked[-2:]

    if score >= 0.72:
        tone_head = "This pairing feels polished and intentional."
    elif score >= 0.62:
        tone_head = "This pairing is solid and wearable."
    elif score >= 0.55:
        tone_head = "This pairing is workable with light styling tweaks."
    elif score >= 0.45:
        tone_head = "This pairing is borderline, but still salvageable with targeted adjustments."
    else:
        tone_head = "This pairing struggles in its current form."

    if relation == "monochrome":
        color_line = f"The {top_color} + {bottom_color} monochrome base is clean and easy to style."
    elif relation == "neutral-anchor":
        color_line = f"The palette works because one side acts as a neutral anchor ({top_color}/{bottom_color})."
    elif relation == "contrast":
        color_line = "The color contrast gives energy, but needs one clean anchor to stay intentional."
    else:
        color_line = "The color relation is acceptable, though it is not the strongest styling signal here."

    why = [
        _component_phrase(strongest[0][0], strong=True),
        color_line,
    ]
    if top_pattern and bottom_pattern and len(why) < 3:
        why.append(
            f"Pattern mix ({top_pattern} + {bottom_pattern}) feels intentional, so texture rhythm stays controlled."
        )
    if strongest[1][1] >= 0.7:
        why.append(_component_phrase(strongest[1][0], strong=True))

    risk = [
        _component_phrase(weakest[0][0], strong=False),
    ]
    if weakest[1][1] < 0.62:
        risk.append(_component_phrase(weakest[1][0], strong=False))

    if weakest[0][0] == "model":
        suggestion = (
            f"Keep the {top_cat.lower()} or {bottom_cat.lower()} you prefer, then swap the other to a cleaner cut to improve silhouette continuity."
        )
    elif weakest[0][0] == "type_prior":
        suggestion = "Add one structure anchor (belt, blazer, or sharper shoes) so the pairing looks more deliberate."
    elif weakest[0][0] == "color":
        suggestion = "Shift one piece toward a neutral or neighboring hue to reduce color friction while keeping the same vibe."
    elif weakest[0][0] == "brightness":
        suggestion = "Introduce one clearly lighter or darker accessory/layer so the outfit has stronger depth separation."
    else:
        suggestion = "Add texture via bag, shoes, or outer layer instead of introducing another loud pattern."

    if relation == "monochrome":
        suggestion = (
            f"Keep the monochrome base, then add one sharp accent (metal, dark belt, or structured bag) to create a focal point."
        )

    summary = f"{tone_head} {top_cat} + {bottom_cat} is currently {label.lower()} ({score:.2f})."
    current_conf = _to_text(current.get("confidence_note"), "").lower()
    if current_conf not in {"high", "medium", "low"}:
        current_conf = "high" if score >= 0.72 else "medium" if score >= 0.55 else "low"

    return {
        "summary": summary,
        "why_it_works": why[:3],
        "risk_points": risk[:2],
        "style_suggestion": suggestion,
        "confidence_note": current_conf,
        "disclaimer": "Explanation only; score and label are unchanged.",
    }


def _looks_robotic(explanation: dict[str, object]) -> bool:
    text = " ".join(
        [
            _to_text(explanation.get("summary"), ""),
            _to_text(explanation.get("style_suggestion"), ""),
            " ".join(_split_clean_points(explanation.get("why_it_works"), 4)),
            " ".join(_split_clean_points(explanation.get("risk_points"), 3)),
        ]
    ).lower()
    markers = [
        "component",
        "final score",
        "some viewers",
        "optimal fit and comfort",
        "indicating an overall",
        "borderline acceptable with a final score",
        "[",
        "]",
    ]
    if any(m in text for m in markers):
        return True
    if len(_to_text(explanation.get("summary"), "").split()) < 7:
        return True
    return False


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate Ollama explanation from prepared facts JSON.")
    p.add_argument("--facts-json", required=True, help="Path to facts JSON file")
    p.add_argument(
        "--config",
        default=str(ROOT / "configs" / "pipeline_config.json"),
        help="Path to pipeline config JSON",
    )
    p.add_argument(
        "--json-out",
        default="",
        help="Optional JSON output path",
    )
    p.add_argument(
        "--public-output",
        action="store_true",
        help="Accepted for compatibility with runner; not used here.",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    facts_path = Path(args.facts_json)
    if not facts_path.exists():
        raise FileNotFoundError(f"Facts JSON not found: {facts_path}")

    facts_obj = json.loads(facts_path.read_text(encoding="utf-8"))
    if not isinstance(facts_obj, dict):
        raise ValueError("Facts JSON must be an object.")

    cfg = PipelineConfig.from_json(args.config)
    explainer = OllamaExplainer(cfg=cfg.ollama, cache_dir=cfg.paths.cache_dir)
    llm = explainer.explain(facts=facts_obj)

    explanation_obj = llm.explanation
    effective_status = llm.status
    llm_source = "ollama"
    if explanation_obj is None:
        explanation_obj = _fallback_explanation(facts_obj)
        effective_status = "fallback"
        llm_source = "fallback"
    elif str(llm.source).strip():
        llm_source = str(llm.source).strip()

    explanation_obj = _normalize_explanation_shape(_as_dict(explanation_obj))
    if _looks_robotic(explanation_obj):
        explanation_obj = _compose_human_rewrite(facts_obj, explanation_obj)
        if llm_source != "fallback":
            llm_source = f"{llm_source}_rewritten"

    payload: dict[str, object] = {
        "llm_status": effective_status,
        "llm_cached": bool(llm.cached),
        "llm_source": llm_source,
    }
    if explanation_obj is not None:
        payload["llm_explanation"] = explanation_obj
    if llm.status != "ok" and llm.raw:
        payload["llm_raw"] = llm.raw
    if llm.error:
        payload["llm_error"] = llm.error

    print(json.dumps(payload, indent=2))
    if args.json_out:
        out_path = Path(args.json_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
