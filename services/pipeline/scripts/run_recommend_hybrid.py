from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from hashlib import sha1
from pathlib import Path
import sys
from typing import Any, Dict, List

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from outfit_pipeline.engine import OutfitCompatibilityPipeline, RetrievalMode
from outfit_pipeline.features import pattern_tags
from outfit_pipeline.pattern_model import PatternPrediction

_DETECT_CONFIDENCE_TRUST = 0.35
_DETECT_CONFIDENCE_MARGIN = 0.06
_UPPER_VISIBILITY = {"upper_body", "upper_partial"}
_LOWER_VISIBILITY = {"mid_lower", "lower_partial"}
_FAST_WARDROBE_PREFILTER_K = 24
_WARDROBE_MIN_SCORE_DEFAULT = 0.55
_WARDROBE_FLOOR_SCORE_DEFAULT = 0.45


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Hybrid top-K recommendation: wardrobe-first, then Polyvore fallback.",
    )
    p.add_argument("--image", required=True, help="Path to uploaded query image")
    p.add_argument(
        "--mode",
        default="auto",
        choices=["auto", "top2bottom", "bottom2top"],
        help="Recommendation mode. Use auto to detect from image.",
    )
    p.add_argument("--wardrobe-json", required=True, help="Path to wardrobe candidate JSON array")
    p.add_argument("--top-k", type=int, default=3, help="How many ranked results to return")
    p.add_argument(
        "--shortlist-k",
        type=int,
        default=50,
        help="Shortlist size for Polyvore fallback rerank",
    )
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
        help="Redact local filesystem paths in output payload",
    )
    p.add_argument(
        "--bg-method",
        default="",
        choices=["", "none", "rembg", "u2net", "u2netp", "isnet", "segformer"],
        help="Optional foreground method override",
    )
    p.add_argument(
        "--defer-llm",
        action="store_true",
        help="Skip Ollama explanation during this call.",
    )
    p.add_argument(
        "--fast",
        action="store_true",
        help="Low-latency mode: disable heavy pattern inference and cap shortlist.",
    )
    p.add_argument(
        "--wardrobe-min-score",
        type=float,
        default=_WARDROBE_MIN_SCORE_DEFAULT,
        help="Strong-match threshold for wardrobe recommendations.",
    )
    p.add_argument(
        "--wardrobe-floor-score",
        type=float,
        default=_WARDROBE_FLOOR_SCORE_DEFAULT,
        help="Fallback floor. If best wardrobe score is below this, use Polyvore fallback.",
    )
    p.add_argument(
        "--disable-polyvore-fallback",
        action="store_true",
        help="Return wardrobe matches only. Do not fill missing slots from Polyvore.",
    )
    return p.parse_args()


def _safe_detect_mode(pipe: OutfitCompatibilityPipeline, query_path: Path) -> tuple[RetrievalMode, dict[str, object]]:
    def _pack(
        *,
        semantic: str,
        source: str,
        category: str,
        confidence: float,
        reason: str,
        status: str = "resolved",
        extras: dict[str, object] | None = None,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "semantic": semantic,
            "source": source,
            "category": category,
            "confidence": confidence,
            "reason": reason,
            "status": status,
        }
        if extras:
            payload.update(extras)
        return payload

    try:
        meta = pipe._infer_meta_from_path(query_path, semantic_hint="")
        semantic = str(getattr(meta, "semantic", "") or "").strip().lower()
        source = str(getattr(meta, "category_source", "") or "").strip().lower()
        category = str(getattr(meta, "category_name", "") or "").strip()
        confidence = float(getattr(meta, "category_confidence", 0.0))

        if semantic == "tops" and confidence >= _DETECT_CONFIDENCE_TRUST:
            return "top2bottom", _pack(
                semantic=semantic,
                source=source,
                category=category,
                confidence=confidence,
                reason="semantic_detected",
            )
        if semantic == "bottoms" and confidence >= _DETECT_CONFIDENCE_TRUST:
            return "bottom2top", _pack(
                semantic=semantic,
                source=source,
                category=category,
                confidence=confidence,
                reason="semantic_detected",
            )

        top_crop_path, top_crop = pipe._prepare_input_path(query_path, semantic_hint="tops")
        visibility = str(getattr(top_crop, "body_visibility", "") or "").strip().lower()
        if visibility in _UPPER_VISIBILITY:
            return "top2bottom", _pack(
                semantic="tops",
                source="autocrop_visibility",
                category=category,
                confidence=float(getattr(top_crop, "confidence", 0.0)),
                reason="yolo_visibility_upper",
                extras={"body_visibility": visibility},
            )
        if visibility in _LOWER_VISIBILITY:
            return "bottom2top", _pack(
                semantic="bottoms",
                source="autocrop_visibility",
                category=category,
                confidence=float(getattr(top_crop, "confidence", 0.0)),
                reason="yolo_visibility_lower",
                extras={"body_visibility": visibility},
            )

        bottom_crop_path, bottom_crop = pipe._prepare_input_path(query_path, semantic_hint="bottoms")
        top_meta = pipe._infer_meta_from_path(top_crop_path, semantic_hint="tops")
        bottom_meta = pipe._infer_meta_from_path(bottom_crop_path, semantic_hint="bottoms")
        top_conf = float(getattr(top_meta, "category_confidence", 0.0))
        bottom_conf = float(getattr(bottom_meta, "category_confidence", 0.0))
        if (
            top_conf >= _DETECT_CONFIDENCE_TRUST
            and bottom_conf >= _DETECT_CONFIDENCE_TRUST
            and abs(top_conf - bottom_conf) < _DETECT_CONFIDENCE_MARGIN
        ):
            preferred_mode: RetrievalMode = "top2bottom" if top_conf >= bottom_conf else "bottom2top"
            preferred_semantic = "tops" if preferred_mode == "top2bottom" else "bottoms"
            return preferred_mode, _pack(
                semantic=preferred_semantic,
                source="crop_confidence",
                category=category,
                confidence=max(top_conf, bottom_conf),
                reason="ambiguous_both_detected_close_confidence",
                status="ambiguous",
                extras={
                    "top_crop_confidence": top_conf,
                    "bottom_crop_confidence": bottom_conf,
                    "body_visibility": visibility or str(getattr(bottom_crop, "body_visibility", "") or "unknown"),
                    "recommended_mode": preferred_mode,
                    "choices": [
                        {"mode": "top2bottom", "label": "Use Top"},
                        {"mode": "bottom2top", "label": "Use Bottom"},
                    ],
                },
            )

        if top_conf >= bottom_conf + _DETECT_CONFIDENCE_MARGIN:
            return "top2bottom", _pack(
                semantic="tops",
                source="crop_confidence",
                category=str(getattr(top_meta, "category_name", "") or category),
                confidence=top_conf,
                reason="crop_confidence_compare",
                extras={
                    "top_crop_confidence": top_conf,
                    "bottom_crop_confidence": bottom_conf,
                    "body_visibility": visibility or str(getattr(bottom_crop, "body_visibility", "") or "unknown"),
                },
            )
        if bottom_conf >= top_conf + _DETECT_CONFIDENCE_MARGIN:
            return "bottom2top", _pack(
                semantic="bottoms",
                source="crop_confidence",
                category=str(getattr(bottom_meta, "category_name", "") or category),
                confidence=bottom_conf,
                reason="crop_confidence_compare",
                extras={
                    "top_crop_confidence": top_conf,
                    "bottom_crop_confidence": bottom_conf,
                    "body_visibility": visibility or str(getattr(bottom_crop, "body_visibility", "") or "unknown"),
                },
            )

        if semantic == "tops":
            return "top2bottom", _pack(
                semantic=semantic,
                source=source or "image_model",
                category=category,
                confidence=confidence,
                reason="fallback_semantic_tops",
                extras={
                    "top_crop_confidence": top_conf,
                    "bottom_crop_confidence": bottom_conf,
                    "body_visibility": visibility or str(getattr(bottom_crop, "body_visibility", "") or "unknown"),
                },
            )
        if semantic == "bottoms":
            return "bottom2top", _pack(
                semantic=semantic,
                source=source or "image_model",
                category=category,
                confidence=confidence,
                reason="fallback_semantic_bottoms",
                extras={
                    "top_crop_confidence": top_conf,
                    "bottom_crop_confidence": bottom_conf,
                    "body_visibility": visibility or str(getattr(bottom_crop, "body_visibility", "") or "unknown"),
                },
            )

        return "top2bottom", _pack(
            semantic=semantic or "unknown",
            source=source or "unknown",
            category=category,
            confidence=confidence,
            reason="unknown_semantic_default_top2bottom",
            extras={
                "top_crop_confidence": top_conf,
                "bottom_crop_confidence": bottom_conf,
                "body_visibility": visibility or str(getattr(bottom_crop, "body_visibility", "") or "unknown"),
            },
        )
    except Exception as exc:  # noqa: BLE001
        return "top2bottom", {
            "semantic": "unknown",
            "source": "none",
            "category": "",
            "confidence": 0.0,
            "reason": "detect_failed_default_top2bottom",
            "error": str(exc),
        }


def _safe_semantic(raw: object) -> str:
    value = str(raw or "").strip().lower()
    if value in {"top", "tops"}:
        return "tops"
    if value in {"bottom", "bottoms"}:
        return "bottoms"
    return ""


def _basename(path_or_name: object) -> str:
    return Path(str(path_or_name or "")).name


def _read_wardrobe_candidates(path: Path) -> list[dict[str, object]]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, list):
        return []
    out: list[dict[str, object]] = []
    for row in obj:
        if not isinstance(row, dict):
            continue
        local_path = Path(str(row.get("local_path") or "")).resolve()
        if not local_path.exists():
            continue
        semantic = _safe_semantic(row.get("category") or row.get("semantic"))
        if not semantic:
            continue
        nested_details = row.get("details") if isinstance(row.get("details"), dict) else {}
        wardrobe_name = str(
            row.get("name")
            or nested_details.get("name")
            or nested_details.get("description")
            or ""
        ).strip()
        out.append(
            {
                "item_id": str(row.get("item_id") or row.get("id") or local_path.stem),
                "local_path": str(local_path),
                "semantic": semantic,
                "image_url": str(row.get("image_url") or "").strip() or f"/uploads/{local_path.name}",
                "name": wardrobe_name,
                "features": row.get("features") if isinstance(row.get("features"), dict) else None,
            }
        )
    return out


def _make_pattern_prediction(
    *,
    top_label: str,
    top_prob: float,
    patterned: bool,
    labels: list[str] | None = None,
    probs: list[float] | None = None,
    threshold: float = 0.35,
) -> PatternPrediction:
    label = str(top_label or "").strip() or "solid"
    p = float(max(0.0, min(1.0, top_prob)))
    th = float(max(0.0, min(1.0, threshold)))
    lbls = [str(x).strip() for x in (labels or []) if str(x).strip()]
    if label not in lbls:
        lbls.insert(0, label)
    if not lbls:
        lbls = [label]

    if probs and len(probs) == len(lbls):
        pr = [float(max(0.0, min(1.0, x))) for x in probs]
    else:
        pr = [0.0 for _ in lbls]
        pr[0] = p

    return PatternPrediction(
        labels=lbls,
        probs=pr,
        threshold=th,
        top_label=label,
        top_prob=p,
        patterned=bool(patterned),
    )


def _pattern_prediction_from_text(text: str) -> PatternPrediction:
    tags = sorted(pattern_tags(text or ""))
    patterned = not (len(tags) == 1 and tags[0] == "solid")
    if patterned:
        top_label = next((t for t in tags if t != "solid"), tags[0] if tags else "print")
        top_prob = 0.8
    else:
        top_label = "solid"
        top_prob = 0.2
    return _make_pattern_prediction(
        top_label=top_label,
        top_prob=top_prob,
        patterned=patterned,
        labels=tags if tags else [top_label],
        threshold=0.35,
    )


def _pattern_prediction_from_features(features: object) -> PatternPrediction | None:
    if not isinstance(features, dict):
        return None
    pat = features.get("pattern")
    if not isinstance(pat, dict):
        return None

    top_label = str(pat.get("top_label", "") or "").strip()
    top_prob_raw = pat.get("top_prob", 0.0)
    top_prob = float(top_prob_raw) if isinstance(top_prob_raw, (int, float)) else 0.0
    patterned_raw = pat.get("patterned", None)
    patterned = bool(patterned_raw) if isinstance(patterned_raw, bool) else bool(top_label and top_label != "solid")
    threshold_raw = pat.get("threshold", 0.35)
    threshold = float(threshold_raw) if isinstance(threshold_raw, (int, float)) else 0.35

    labels_raw = pat.get("labels", [])
    labels = [str(x).strip() for x in labels_raw if str(x).strip()] if isinstance(labels_raw, list) else []
    topk_raw = pat.get("topk", [])
    probs_map: dict[str, float] = {}
    if isinstance(topk_raw, list):
        for row in topk_raw:
            if not isinstance(row, dict):
                continue
            name = str(row.get("label", "") or "").strip()
            prob_raw = row.get("prob", 0.0)
            if not name:
                continue
            prob = float(prob_raw) if isinstance(prob_raw, (int, float)) else 0.0
            probs_map[name] = float(max(0.0, min(1.0, prob)))

    if not labels and probs_map:
        labels = list(probs_map.keys())
    if not labels and top_label:
        labels = [top_label]

    probs = [probs_map.get(lbl, top_prob if lbl == top_label else 0.0) for lbl in labels] if labels else None
    return _make_pattern_prediction(
        top_label=top_label or (labels[0] if labels else "solid"),
        top_prob=top_prob,
        patterned=patterned,
        labels=labels,
        probs=probs,
        threshold=threshold,
    )


def _clip01(x: float) -> float:
    return float(max(0.0, min(1.0, x)))


def _hue_distance_deg(a: float, b: float) -> float:
    d = abs(float(a) - float(b))
    return float(min(d, 360.0 - d))


def _is_neutral(name: str) -> bool:
    return str(name or "").strip().lower() in {"black", "white", "gray"}


def _heuristic_color_score(
    q_name: str,
    q_hue: float | None,
    q_value: float | None,
    c_name: str,
    c_hue: float | None,
    c_value: float | None,
) -> float:
    if _is_neutral(q_name) or _is_neutral(c_name):
        base = 0.82
    elif q_hue is not None and c_hue is not None:
        d = _hue_distance_deg(q_hue, c_hue)
        if d <= 20:
            base = 0.76
        elif d <= 55:
            base = 0.90
        elif 150 <= d <= 210:
            base = 0.88
        else:
            base = 0.64
    else:
        base = 0.72

    if q_value is not None and c_value is not None:
        vd = abs(float(q_value) - float(c_value))
        if 25 <= vd <= 110:
            base += 0.06
    return _clip01(base)


def _heuristic_brightness_score(q_b: float | None, c_b: float | None) -> float:
    if q_b is None or c_b is None:
        return 0.5
    bdiff = abs(float(q_b) - float(c_b))
    return _clip01(float(np.exp(-((bdiff - 22.0) ** 2) / (2.0 * (20.0 ** 2)))))


def _heuristic_pattern_score(
    q_patterned: bool | None,
    q_label: str,
    c_patterned: bool | None,
    c_label: str,
) -> float:
    if q_patterned is None or c_patterned is None:
        return 0.7
    if (not q_patterned) and (not c_patterned):
        return 0.84
    if q_patterned != c_patterned:
        return 0.90
    if str(q_label).strip().lower() == str(c_label).strip().lower() and str(q_label).strip():
        return 0.78
    return 0.63


def _quick_prefilter_score(candidate: dict[str, object], query_vis, query_pat) -> float:
    features = candidate.get("features")
    if not isinstance(features, dict):
        return 0.5

    q_primary = query_vis.colors[0] if query_vis.colors else None
    q_name = str(getattr(q_primary, "name", "") or "")
    q_hue = float(getattr(q_primary, "hue_deg", 0.0)) if q_primary is not None else None
    q_value = float(getattr(q_primary, "value", 0.0)) if q_primary is not None else None

    c_color = features.get("color") if isinstance(features.get("color"), dict) else {}
    c_palette = c_color.get("palette") if isinstance(c_color, dict) else []
    c_primary = c_palette[0] if isinstance(c_palette, list) and c_palette and isinstance(c_palette[0], dict) else {}
    c_name = str(c_color.get("primary", "") or c_primary.get("name", ""))
    c_hue_raw = c_primary.get("hue_deg", None)
    c_value_raw = c_primary.get("value", None)
    c_hue = float(c_hue_raw) if isinstance(c_hue_raw, (int, float)) else None
    c_value = float(c_value_raw) if isinstance(c_value_raw, (int, float)) else None

    c_metrics = features.get("metrics") if isinstance(features.get("metrics"), dict) else {}
    c_brightness_raw = c_metrics.get("brightness", None)
    c_brightness = float(c_brightness_raw) if isinstance(c_brightness_raw, (int, float)) else None

    q_patterned = bool(query_pat.patterned) if query_pat is not None else None
    q_pattern_label = str(query_pat.top_label) if query_pat is not None else ""
    c_pattern = features.get("pattern") if isinstance(features.get("pattern"), dict) else {}
    c_patterned = c_pattern.get("patterned", None)
    c_patterned_bool = bool(c_patterned) if isinstance(c_patterned, bool) else None
    c_pattern_label = str(c_pattern.get("top_label", "") or "")

    color_score = _heuristic_color_score(q_name, q_hue, q_value, c_name, c_hue, c_value)
    brightness_score = _heuristic_brightness_score(query_vis.metrics.brightness, c_brightness)
    pattern_score = _heuristic_pattern_score(q_patterned, q_pattern_label, c_patterned_bool, c_pattern_label)
    return _clip01(0.45 * color_score + 0.35 * brightness_score + 0.20 * pattern_score)


def _score_wardrobe_candidates(
    pipe: OutfitCompatibilityPipeline,
    *,
    mode: RetrievalMode,
    query_input_path: Path,
    wardrobe_candidates: list[dict[str, object]],
    fast_mode: bool = False,
) -> list[dict[str, object]]:
    query_semantic_hint = "tops" if mode == "top2bottom" else "bottoms"
    target_semantic = "bottoms" if mode == "top2bottom" else "tops"

    query_path, query_crop = pipe._prepare_input_path(query_input_path, semantic_hint=query_semantic_hint)
    query_meta = pipe._infer_meta_from_path(query_path, semantic_hint=query_semantic_hint)
    query_emb = pipe._encode_image(query_path)
    query_vis, query_mask = pipe._visual_for_path(query_path, cache_key=query_meta.item_id or str(query_path))
    query_pat = pipe._pattern_for_path(query_path, cache_key=query_meta.item_id or str(query_path))
    if query_pat is None and fast_mode:
        query_pat = _pattern_prediction_from_text(query_meta.text)

    usable_candidates: list[dict[str, object]] = [
        c for c in wardrobe_candidates if str(c.get("semantic", "")) == target_semantic
    ]
    if fast_mode and len(usable_candidates) > _FAST_WARDROBE_PREFILTER_K:
        scored = [
            (_quick_prefilter_score(candidate=c, query_vis=query_vis, query_pat=query_pat), c)
            for c in usable_candidates
        ]
        scored.sort(key=lambda x: float(x[0]), reverse=True)
        usable_candidates = [row[1] for row in scored[:_FAST_WARDROBE_PREFILTER_K]]

    rows: list[dict[str, object]] = []
    for candidate in usable_candidates:
        cand_input_path = Path(str(candidate.get("local_path") or ""))
        if not cand_input_path.exists():
            continue
        cand_path, _ = pipe._prepare_input_path(cand_input_path, semantic_hint=target_semantic)
        cand_meta = pipe._infer_meta_from_path(cand_path, semantic_hint=target_semantic)
        cand_emb = pipe._encode_image(cand_path)
        cand_vis, cand_mask = pipe._visual_for_path(cand_path, cache_key=cand_meta.item_id or str(cand_path))
        if fast_mode:
            cand_pat = _pattern_prediction_from_features(candidate.get("features"))
            if cand_pat is None:
                cand_pat = _pattern_prediction_from_text(cand_meta.text)
        else:
            cand_pat = pipe._pattern_for_path(cand_path, cache_key=cand_meta.item_id or str(cand_path))
        model_score = float(
            pipe._model_scores_batch(query_emb[np.newaxis, :], cand_emb[np.newaxis, :])[0]
            if mode == "top2bottom"
            else pipe._model_scores_batch(cand_emb[np.newaxis, :], query_emb[np.newaxis, :])[0]
        )

        if mode == "top2bottom":
            top_meta, bottom_meta = query_meta, cand_meta
            top_vis, bottom_vis = query_vis, cand_vis
            top_pat, bottom_pat = query_pat, cand_pat
        else:
            top_meta, bottom_meta = cand_meta, query_meta
            top_vis, bottom_vis = cand_vis, query_vis
            top_pat, bottom_pat = cand_pat, query_pat

        score, details = pipe._fuse(
            model_score=model_score,
            top_meta=top_meta,
            bottom_meta=bottom_meta,
            top_features=top_vis,
            bottom_features=bottom_vis,
            top_pattern=top_pat,
            bottom_pattern=bottom_pat,
        )
        details["query_item_id"] = query_meta.item_id
        details["query_semantic"] = query_meta.semantic
        details["query_category"] = query_meta.category
        details["query_category_name"] = query_meta.category_name or query_meta.category
        details["query_category_source"] = query_meta.category_source
        details["query_category_confidence"] = float(query_meta.category_confidence)
        details["query_mask_fallback"] = bool(query_mask.used_fallback)
        details["candidate_mask_fallback"] = bool(cand_mask.used_fallback)
        details["query_autocrop"] = {
            "applied": bool(query_crop.applied),
            "reason": query_crop.reason,
            "processed_path": str(query_path),
            "body_visibility": query_crop.body_visibility,
            "confidence": float(query_crop.confidence),
            "crop_box": list(query_crop.crop_box) if query_crop.crop_box else None,
            "error": query_crop.error,
        }
        details["autocrop_model_error"] = pipe.auto_cropper.model_error
        details["candidate_category"] = cand_meta.category
        details["candidate_category_name"] = cand_meta.category_name or cand_meta.category
        details["candidate_category_source"] = "wardrobe"
        details["candidate_category_confidence"] = float(cand_meta.category_confidence)
        details["source"] = "wardrobe"
        details["wardrobe_name"] = str(candidate.get("name") or "")
        details["llm_status"] = "deferred"
        details["llm_cached"] = False

        rows.append(
            {
                "item_id": str(candidate.get("item_id") or ""),
                "image_path": str(cand_path),
                "image_url": str(candidate.get("image_url") or ""),
                "semantic_category": str(candidate.get("semantic") or ""),
                "source": "wardrobe",
                "score": score,
                "details": details,
            }
        )

    rows.sort(key=lambda x: float(x["score"].final), reverse=True)
    return rows


def _semantic_fallback_preview(
    pipe: OutfitCompatibilityPipeline,
    candidate_path: Path,
    semantic: str,
    yolo_reason: str,
) -> tuple[str, dict[str, object]]:
    sem = str(semantic or "").strip().lower()
    try:
        st = candidate_path.stat()
    except Exception as exc:  # noqa: BLE001
        return "", {
            "applied": False,
            "reason": "fallback_stat_failed",
            "semantic_hint": sem,
            "body_visibility": "unknown",
            "confidence": 0.0,
            "crop_box": None,
            "error": str(exc),
            "yolo_reason": yolo_reason,
        }

    key_raw = "|".join(
        [
            "semantic_fallback_v1",
            str(candidate_path.resolve()),
            str(st.st_size),
            str(st.st_mtime_ns),
            sem,
            yolo_reason,
        ]
    )
    out_name = f"{sha1(key_raw.encode('utf-8')).hexdigest()}.jpg"
    out_path = pipe.auto_cropper.cache_dir / out_name

    if out_path.exists():
        return f"/pipeline-autocrop/{out_name}", {
            "applied": True,
            "reason": f"semantic_fallback_after_{yolo_reason or 'yolo_skip'}",
            "semantic_hint": sem,
            "body_visibility": "upper_body" if sem == "tops" else "mid_lower" if sem == "bottoms" else "unknown",
            "confidence": 0.0,
            "crop_box": None,
            "error": "",
            "yolo_reason": yolo_reason,
        }

    img_bgr = cv2.imread(str(candidate_path))
    if img_bgr is None:
        return "", {
            "applied": False,
            "reason": "fallback_read_failed",
            "semantic_hint": sem,
            "body_visibility": "unknown",
            "confidence": 0.0,
            "crop_box": None,
            "error": "cv2.imread returned None",
            "yolo_reason": yolo_reason,
        }

    h, w = img_bgr.shape[:2]
    if h < 4 or w < 4:
        return "", {
            "applied": False,
            "reason": "fallback_image_too_small",
            "semantic_hint": sem,
            "body_visibility": "unknown",
            "confidence": 0.0,
            "crop_box": None,
            "error": "",
            "yolo_reason": yolo_reason,
        }

    if sem == "tops":
        y1, y2 = 0, max(2, int(round(h * 0.62)))
    elif sem == "bottoms":
        y1, y2 = min(h - 2, int(round(h * 0.42))), h
    else:
        y1, y2 = int(round(h * 0.2)), int(round(h * 0.8))

    y1 = max(0, min(y1, h - 2))
    y2 = max(y1 + 2, min(y2, h))
    crop = img_bgr[y1:y2, :].copy()
    if crop.size == 0:
        return "", {
            "applied": False,
            "reason": "fallback_empty_crop",
            "semantic_hint": sem,
            "body_visibility": "unknown",
            "confidence": 0.0,
            "crop_box": [0, y1, w, y2],
            "error": "",
            "yolo_reason": yolo_reason,
        }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    ok = cv2.imwrite(str(out_path), crop)
    if not ok:
        return "", {
            "applied": False,
            "reason": "fallback_write_failed",
            "semantic_hint": sem,
            "body_visibility": "unknown",
            "confidence": 0.0,
            "crop_box": [0, y1, w, y2],
            "error": "",
            "yolo_reason": yolo_reason,
        }

    return f"/pipeline-autocrop/{out_name}", {
        "applied": True,
        "reason": f"semantic_fallback_after_{yolo_reason or 'yolo_skip'}",
        "semantic_hint": sem,
        "body_visibility": "upper_body" if sem == "tops" else "mid_lower" if sem == "bottoms" else "unknown",
        "confidence": 0.0,
        "crop_box": [0, y1, w, y2],
        "error": "",
        "yolo_reason": yolo_reason,
    }


def _polyvore_preview_for_candidate(
    pipe: OutfitCompatibilityPipeline,
    candidate_path: Path,
    semantic: str,
) -> tuple[str, dict[str, object]]:
    sem = str(semantic or "").strip().lower()
    if sem not in {"tops", "bottoms"}:
        return "", {
            "applied": False,
            "reason": "unsupported_semantic",
            "semantic_hint": sem,
            "body_visibility": "unknown",
            "confidence": 0.0,
            "crop_box": None,
            "error": "",
        }

    try:
        crop_path, decision = pipe.auto_cropper.prepare(candidate_path, semantic_hint=sem)
    except Exception as exc:  # noqa: BLE001
        return "", {
            "applied": False,
            "reason": "exception",
            "semantic_hint": sem,
            "body_visibility": "unknown",
            "confidence": 0.0,
            "crop_box": None,
            "error": str(exc),
        }

    meta = {
        "applied": bool(decision.applied),
        "reason": str(decision.reason),
        "semantic_hint": sem,
        "body_visibility": str(decision.body_visibility),
        "confidence": float(decision.confidence),
        "crop_box": list(decision.crop_box) if decision.crop_box else None,
        "error": str(decision.error or ""),
    }
    if decision.applied and crop_path.exists():
        return f"/pipeline-autocrop/{crop_path.name}", meta

    fb_url, fb_meta = _semantic_fallback_preview(
        pipe=pipe,
        candidate_path=candidate_path,
        semantic=sem,
        yolo_reason=str(decision.reason),
    )
    if fb_url:
        return fb_url, fb_meta
    return "", meta


def main() -> None:
    args = parse_args()
    pipe = OutfitCompatibilityPipeline(config_path=args.config)
    if args.bg_method:
        pipe.set_foreground_method(args.bg_method)

    query_path = Path(args.image)
    if not query_path.exists():
        raise FileNotFoundError(f"Image not found: {query_path}")

    wardrobe_path = Path(args.wardrobe_json)
    if not wardrobe_path.exists():
        raise FileNotFoundError(f"Wardrobe JSON not found: {wardrobe_path}")
    wardrobe_candidates = _read_wardrobe_candidates(wardrobe_path)

    if args.mode == "auto":
        mode, detection = _safe_detect_mode(pipe, query_path=query_path)
        if str(detection.get("status", "")).strip().lower() == "ambiguous":
            payload: dict[str, object] = {
                "query_image": _basename(str(query_path)) if args.public_output else str(query_path),
                "mode": "ambiguous",
                "top_k": max(1, int(args.top_k)),
                "shortlist_k": min(max(10, int(args.shortlist_k)), 25) if args.fast else max(10, int(args.shortlist_k)),
                "fast_mode": bool(args.fast),
                "semantic_detection": detection,
                "message": "Ambiguous input detected. Please choose whether to treat this image as top or bottom.",
                "requires_user_choice": True,
                "quality_gate": {
                    "wardrobe_min_score": float(max(0.0, min(1.0, float(args.wardrobe_min_score)))),
                    "wardrobe_floor_score": float(max(0.0, min(1.0, float(args.wardrobe_floor_score)))),
                    "wardrobe_total_candidates": len(wardrobe_candidates),
                    "wardrobe_strong_candidates": 0,
                    "wardrobe_best_score": None,
                    "fallback_triggered": False,
                    "fallback_reason": "awaiting_user_choice",
                },
                "source_mix": {
                    "wardrobe_count": 0,
                    "polyvore_count": 0,
                },
                "fallback_policy": {
                    "allow_polyvore_fallback": not bool(args.disable_polyvore_fallback),
                    "polyvore_fallback_used": False,
                },
                "results": [],
            }
            print(json.dumps(payload, indent=2))
            if args.json_out:
                out_path = Path(args.json_out)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
                print(f"\nSaved: {out_path}")
            return
    else:
        mode = args.mode  # type: ignore[assignment]
        detection = {
            "semantic": "forced",
            "source": "client",
            "category": "",
            "confidence": 1.0,
            "reason": "mode_forced_by_client",
            "status": "forced",
            "forced_mode": mode,
        }
    top_k = max(1, int(args.top_k))
    shortlist_k = min(max(10, int(args.shortlist_k)), 25) if args.fast else max(10, int(args.shortlist_k))
    wardrobe_min_score = float(max(0.0, min(1.0, float(args.wardrobe_min_score))))
    wardrobe_floor_score = float(max(0.0, min(1.0, float(args.wardrobe_floor_score))))
    if wardrobe_floor_score > wardrobe_min_score:
        wardrobe_floor_score = wardrobe_min_score

    wardrobe_ranked = _score_wardrobe_candidates(
        pipe,
        mode=mode,
        query_input_path=query_path,
        wardrobe_candidates=wardrobe_candidates,
        fast_mode=bool(args.fast),
    )
    wardrobe_best_score = (
        float(wardrobe_ranked[0]["score"].final)
        if wardrobe_ranked and isinstance(wardrobe_ranked[0], dict)
        else None
    )
    strong_wardrobe = [
        row for row in wardrobe_ranked
        if float(row["score"].final) >= wardrobe_min_score
    ]
    selected_wardrobe: list[dict[str, object]] = []
    fallback_reason = ""

    if not wardrobe_ranked:
        fallback_reason = "no_wardrobe_candidates"
    elif wardrobe_best_score is not None and wardrobe_best_score < wardrobe_floor_score:
        fallback_reason = "best_wardrobe_below_floor"
    else:
        # Prefer strong wardrobe matches first.
        selected_wardrobe.extend(strong_wardrobe[:top_k])

        # Soft mode: keep wardrobe presence when best is in [floor, min).
        if not selected_wardrobe and wardrobe_ranked:
            selected_wardrobe.append(wardrobe_ranked[0])
            fallback_reason = "soft_keep_best_wardrobe_low_confidence"

        # Fill remaining slots with wardrobe candidates above floor, then Polyvore.
        selected_ids = {str(row.get("item_id") or "") for row in selected_wardrobe}
        for row in wardrobe_ranked:
            if len(selected_wardrobe) >= top_k:
                break
            row_id = str(row.get("item_id") or "")
            if row_id in selected_ids:
                continue
            if float(row["score"].final) >= wardrobe_floor_score:
                selected_wardrobe.append(row)
                selected_ids.add(row_id)

        if not fallback_reason and len(selected_wardrobe) < top_k:
            fallback_reason = "insufficient_wardrobe_candidates_above_floor"

    fallback_triggered = bool(fallback_reason) or (len(selected_wardrobe) < top_k)

    allow_polyvore_fallback = not bool(args.disable_polyvore_fallback)
    remaining = top_k - len(selected_wardrobe)
    poly_rows = []
    if allow_polyvore_fallback and remaining > 0:
        if args.fast:
            # Keep wardrobe pattern checks (query + cached wardrobe features) while
            # disabling heavy per-candidate pattern inference for Polyvore fallback.
            saved_predictor = pipe.pattern_predictor
            saved_pattern_error = pipe.pattern_model_error
            pipe.pattern_predictor = None
            if not pipe.pattern_model_error:
                pipe.pattern_model_error = "disabled_in_fast_mode_polyvore"
            try:
                poly_rows = pipe.rank(
                    mode=mode,
                    query_image=str(query_path),
                    top_k=remaining,
                    shortlist_k=shortlist_k,
                    include_llm=not args.defer_llm,
                )
            finally:
                pipe.pattern_predictor = saved_predictor
                pipe.pattern_model_error = saved_pattern_error
        else:
            poly_rows = pipe.rank(
                mode=mode,
                query_image=str(query_path),
                top_k=remaining,
                shortlist_k=shortlist_k,
                include_llm=not args.defer_llm,
            )
    out_rows: list[dict[str, object]] = []

    for row in selected_wardrobe:
        score = row["score"]
        details = row["details"] if isinstance(row["details"], dict) else {}
        out_rows.append(
            {
                "rank": 0,
                "item_id": str(row["item_id"]),
                "image_path": _basename(row["image_path"]) if args.public_output else str(row["image_path"]),
                "image_url": str(row["image_url"]),
                "semantic_category": str(row["semantic_category"]),
                "source": "wardrobe",
                "final_score": float(score.final),
                "breakdown": asdict(score),
                "details": details,
            }
        )

    for row in poly_rows:
        candidate_path = Path(row.image_path)
        crop_url, crop_meta = _polyvore_preview_for_candidate(
            pipe=pipe,
            candidate_path=candidate_path,
            semantic=row.semantic_category,
        )
        d = row.to_public_dict() if args.public_output else row.to_dict()
        image_name = candidate_path.name
        catalog_url = f"/catalog-images/{image_name}" if image_name else ""
        d["source"] = "polyvore"
        d["image_url"] = crop_url
        details = d.get("details")
        if isinstance(details, dict):
            details["source"] = "polyvore"
            details["candidate_autocrop_preview"] = crop_meta
            details["candidate_catalog_image_url"] = catalog_url
        out_rows.append(d)

    for i, row in enumerate(out_rows, start=1):
        row["rank"] = i

    payload: dict[str, object] = {
        "query_image": _basename(str(query_path)) if args.public_output else str(query_path),
        "mode": mode,
        "top_k": top_k,
        "shortlist_k": shortlist_k,
        "fast_mode": bool(args.fast),
        "semantic_detection": detection,
        "quality_gate": {
            "wardrobe_min_score": wardrobe_min_score,
            "wardrobe_floor_score": wardrobe_floor_score,
            "wardrobe_total_candidates": len(wardrobe_ranked),
            "wardrobe_strong_candidates": len(strong_wardrobe),
            "wardrobe_best_score": wardrobe_best_score,
            "fallback_triggered": fallback_triggered,
            "fallback_reason": fallback_reason,
        },
        "source_mix": {
            "wardrobe_count": len(selected_wardrobe),
            "polyvore_count": len(out_rows) - len(selected_wardrobe),
        },
        "fallback_policy": {
            "allow_polyvore_fallback": allow_polyvore_fallback,
            "polyvore_fallback_used": bool((len(out_rows) - len(selected_wardrobe)) > 0),
        },
        "results": out_rows,
    }

    print(json.dumps(payload, indent=2))
    if args.json_out:
        out_path = Path(args.json_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
