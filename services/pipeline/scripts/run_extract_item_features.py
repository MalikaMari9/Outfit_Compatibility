from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from outfit_pipeline.engine import OutfitCompatibilityPipeline
from outfit_pipeline.features import pattern_tags


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Extract reusable wardrobe features for one clothing image.")
    p.add_argument("--image", required=True, help="Path to wardrobe item image")
    p.add_argument(
        "--semantic",
        default="",
        choices=["", "top", "bottom", "tops", "bottoms"],
        help="Optional semantic hint to guide crop/category model.",
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
    return p.parse_args()


def _semantic_hint(raw: str) -> str:
    v = str(raw or "").strip().lower()
    if v in {"top", "tops"}:
        return "tops"
    if v in {"bottom", "bottoms"}:
        return "bottoms"
    return ""


def _pattern_payload_from_text(meta_text: str) -> dict[str, object]:
    tags = sorted(pattern_tags(meta_text or ""))
    only_solid = tags == ["solid"]
    top = "solid" if only_solid else next((t for t in tags if t != "solid"), tags[0] if tags else "solid")
    return {
        "source": "text_heuristic",
        "top_label": top,
        "top_prob": 0.0,
        "patterned": not only_solid,
        "threshold": 0.35,
        "topk": [{"label": t, "prob": 0.0} for t in tags[:3]],
        "labels": tags,
    }


def _pattern_payload(pred) -> dict[str, object]:
    if pred is None:
        return {
            "source": "none",
            "top_label": "",
            "top_prob": 0.0,
            "patterned": False,
            "threshold": 0.35,
            "topk": [],
            "labels": [],
        }
    return {
        "source": "image_model",
        "top_label": str(pred.top_label),
        "top_prob": float(pred.top_prob),
        "patterned": bool(pred.patterned),
        "threshold": float(pred.threshold),
        "topk": [{"label": str(k), "prob": float(v)} for k, v in pred.topk(3)],
        "labels": [str(x) for x in pred.labels],
    }


def _public_path(path_str: str) -> str:
    return Path(path_str).name if path_str else ""


def main() -> None:
    args = parse_args()
    pipe = OutfitCompatibilityPipeline(config_path=args.config)
    if args.bg_method:
        pipe.set_foreground_method(args.bg_method)

    image_path = Path(args.image)
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    semantic_hint = _semantic_hint(args.semantic)
    prepared_path, crop = pipe._prepare_input_path(image_path, semantic_hint=semantic_hint)
    meta = pipe._infer_meta_from_path(prepared_path, semantic_hint=semantic_hint)
    visual, mask_info = pipe._visual_for_path(prepared_path, cache_key=meta.item_id or str(prepared_path))
    pred = pipe._pattern_for_path(prepared_path, cache_key=meta.item_id or str(prepared_path))

    if pred is None and (meta.text or "").strip():
        pattern = _pattern_payload_from_text(meta.text)
    else:
        pattern = _pattern_payload(pred)

    payload: Dict[str, Any] = {
        "feature_version": "wardrobe_features_v1",
        "semantic": str(meta.semantic or semantic_hint),
        "category_id": str(meta.category or ""),
        "category_name": str(meta.category_name or meta.category or ""),
        "category_source": str(meta.category_source or ""),
        "category_confidence": float(meta.category_confidence),
        "foreground_method": pipe.foreground_method,
        "metrics": asdict(visual.metrics),
        "color": {
            "primary": visual.colors[0].name if visual.colors else "",
            "palette": [asdict(c) for c in visual.colors],
        },
        "pattern": pattern,
        "mask": {
            "coverage": float(visual.mask_coverage),
            "effective_coverage": float(visual.effective_mask_coverage),
            "used_fallback": bool(mask_info.used_fallback),
        },
        "autocrop": {
            "applied": bool(crop.applied),
            "reason": str(crop.reason),
            "semantic_hint": str(crop.semantic_hint),
            "body_visibility": str(crop.body_visibility),
            "confidence": float(crop.confidence),
            "crop_box": list(crop.crop_box) if crop.crop_box else None,
            "error": str(crop.error or ""),
            "processed_path": str(prepared_path),
        },
        "errors": {
            "pattern_model_error": str(pipe.pattern_model_error or ""),
            "category_model_error": str(pipe.category_model_error or ""),
            "autocrop_model_error": str(pipe.auto_cropper.model_error or ""),
        },
    }

    if args.public_output:
        payload["source_image"] = _public_path(str(image_path))
        autocrop = payload.get("autocrop")
        if isinstance(autocrop, dict):
            autocrop["processed_path"] = _public_path(str(autocrop.get("processed_path", "")))
    else:
        payload["source_image"] = str(image_path)

    print(json.dumps(payload, indent=2))
    if args.json_out:
        out_path = Path(args.json_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
