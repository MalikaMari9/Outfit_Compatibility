from __future__ import annotations

import argparse
import json
from hashlib import sha1
from pathlib import Path
import sys

import cv2

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from outfit_pipeline.engine import OutfitCompatibilityPipeline

_DETECT_CONFIDENCE_TRUST = 0.35
_DETECT_CONFIDENCE_MARGIN = 0.06
_UPPER_VISIBILITY = {"upper_body", "upper_partial"}
_LOWER_VISIBILITY = {"mid_lower", "lower_partial"}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Top-K recommendation for one image with automatic top/bottom mode detection.",
    )
    p.add_argument("--image", required=True, help="Path to uploaded image")
    p.add_argument(
        "--mode",
        default="auto",
        choices=["auto", "top2bottom", "bottom2top"],
        help="Retrieval mode. Use auto to detect from image category.",
    )
    p.add_argument("--top-k", type=int, default=5, help="How many ranked results to return")
    p.add_argument(
        "--shortlist-k",
        type=int,
        default=150,
        help="Shortlist size before rerank",
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
    return p.parse_args()


def _safe_detect_mode(pipe: OutfitCompatibilityPipeline, query_path: Path) -> tuple[str, dict[str, object]]:
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
        meta = pipe._infer_meta_from_path(query_path, semantic_hint="")  # internal helper
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

        # Ambiguous query: use YOLO-based crop signals to infer direction.
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

        # For full-body/uncertain visibility, compare category confidence on top- and bottom-focused crops.
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
            preferred_mode = "top2bottom" if top_conf >= bottom_conf else "bottom2top"
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


def _public_query_name(path_str: str) -> str:
    return Path(path_str).name


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
    if args.fast:
        pipe.pattern_predictor = None
        if not pipe.pattern_model_error:
            pipe.pattern_model_error = "disabled_in_fast_mode"

    query_path = Path(args.image)
    if not query_path.exists():
        raise FileNotFoundError(f"Image not found: {query_path}")

    if args.mode == "auto":
        mode, detection = _safe_detect_mode(pipe, query_path=query_path)
        if str(detection.get("status", "")).strip().lower() == "ambiguous":
            payload: dict[str, object] = {
                "query_image": _public_query_name(str(query_path)) if args.public_output else str(query_path),
                "mode": "ambiguous",
                "top_k": int(args.top_k),
                "shortlist_k": min(max(10, int(args.shortlist_k)), 25) if args.fast else int(args.shortlist_k),
                "fast_mode": bool(args.fast),
                "semantic_detection": detection,
                "message": "Ambiguous input detected. Please choose whether to treat this image as top or bottom.",
                "requires_user_choice": True,
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
        mode = args.mode
        detection = {
            "semantic": "forced",
            "source": "cli",
            "category": "",
            "confidence": 1.0,
            "reason": "mode_forced",
            "status": "forced",
            "forced_mode": mode,
        }

    rows = pipe.rank(
        mode=mode,  # type: ignore[arg-type]
        query_image=args.image,
        top_k=max(1, int(args.top_k)),
        shortlist_k=min(max(10, int(args.shortlist_k)), 25) if args.fast else max(10, int(args.shortlist_k)),
        include_llm=not args.defer_llm,
    )
    payload_rows = []
    for row in rows:
        candidate_path = Path(row.image_path)
        crop_url, crop_meta = _polyvore_preview_for_candidate(
            pipe=pipe,
            candidate_path=candidate_path,
            semantic=row.semantic_category,
        )
        item = row.to_public_dict() if args.public_output else row.to_dict()
        image_name = candidate_path.name
        catalog_url = f"/catalog-images/{image_name}" if image_name else ""
        item["source"] = "polyvore"
        item["image_url"] = crop_url
        details = item.get("details")
        if isinstance(details, dict):
            details["source"] = "polyvore"
            details["candidate_autocrop_preview"] = crop_meta
            details["candidate_catalog_image_url"] = catalog_url
        payload_rows.append(item)

    payload: dict[str, object] = {
        "query_image": _public_query_name(str(query_path)) if args.public_output else str(query_path),
        "mode": mode,
        "top_k": int(args.top_k),
        "shortlist_k": min(max(10, int(args.shortlist_k)), 25) if args.fast else int(args.shortlist_k),
        "fast_mode": bool(args.fast),
        "semantic_detection": detection,
        "results": payload_rows,
    }

    print(json.dumps(payload, indent=2))
    if args.json_out:
        out_path = Path(args.json_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
