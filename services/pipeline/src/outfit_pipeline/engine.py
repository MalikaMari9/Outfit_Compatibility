from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha1
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple

import numpy as np
import torch
from PIL import Image

from .config import PipelineConfig, ScoreWeights
from .data import (
    build_embeddings,
    build_type_prior_map,
    default_transform,
    get_item_category,
    infer_item_id_from_path,
    item_text,
    list_items_by_semantic,
    load_bgr,
    load_category_lookup,
    load_embedding_cache,
    load_metadata,
    save_embedding_cache,
    semantic_category,
)
from .features import (
    brightness_compat_score,
    color_harmony_score,
    extract_visual_features_with_mask,
    meaningful_color_palette,
    pattern_compat_score,
)
from .autocrop import AutoBodyCropper, AutoCropDecision
from .segmentation import ForegroundSegmenter, MaskResult
from .ollama_explainer import OllamaExplainer
from .pattern_model import (
    PatternPrediction,
    PatternPredictor,
    pattern_compat_score_from_predictions,
)
from .category_model import CategoryPredictor, infer_semantic_from_category_name
from .modeling import load_pair_model
from .scoring import ScoreBreakdown, combine_scores, label_from_score, type_prior_lookup

RetrievalMode = Literal["top2bottom", "bottom2top"]

_PUBLIC_PATH_KEYS = {
    "top_image",
    "bottom_image",
    "query_image",
    "image_path",
    "processed_path",
    "source_path",
    "output_path",
}


def _redact_path_value(value: str) -> str:
    raw = str(value).strip()
    if not raw:
        return raw
    try:
        name = Path(raw).name
    except Exception:
        return raw
    return name or raw


def _sanitize_public_payload(value: Any, parent_key: str = "") -> Any:
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for k, v in value.items():
            key = str(k)
            key_low = key.lower()
            if isinstance(v, str) and (key_low in _PUBLIC_PATH_KEYS or key_low.endswith("_path")):
                out[key] = _redact_path_value(v)
            else:
                out[key] = _sanitize_public_payload(v, parent_key=key_low)
        return out
    if isinstance(value, list):
        return [_sanitize_public_payload(v, parent_key=parent_key) for v in value]
    if isinstance(value, tuple):
        return tuple(_sanitize_public_payload(v, parent_key=parent_key) for v in value)
    return value


@dataclass
class PairResult:
    top_image: str
    bottom_image: str
    score: ScoreBreakdown
    label: str
    details: Dict[str, object]

    def to_dict(self) -> Dict[str, object]:
        return {
            "top_image": self.top_image,
            "bottom_image": self.bottom_image,
            "label": self.label,
            "final_score": float(self.score.final),
            "breakdown": asdict(self.score),
            "details": self.details,
        }

    def to_public_dict(self) -> Dict[str, object]:
        return _sanitize_public_payload(self.to_dict())


@dataclass
class RankedCandidate:
    rank: int
    item_id: str
    image_path: str
    semantic_category: str
    score: ScoreBreakdown
    details: Dict[str, object]

    def to_dict(self) -> Dict[str, object]:
        return {
            "rank": int(self.rank),
            "item_id": self.item_id,
            "image_path": self.image_path,
            "semantic_category": self.semantic_category,
            "final_score": float(self.score.final),
            "breakdown": asdict(self.score),
            "details": self.details,
        }

    def to_public_dict(self) -> Dict[str, object]:
        return _sanitize_public_payload(self.to_dict())


@dataclass
class _ItemMeta:
    item_id: Optional[str]
    semantic: str
    category: str
    category_name: str
    text: str
    category_source: str
    category_confidence: float


def _norm_rows(x: np.ndarray, eps: float = 1e-12) -> np.ndarray:
    denom = np.linalg.norm(x, axis=1, keepdims=True) + eps
    return x / denom


def _norm_vec(x: np.ndarray, eps: float = 1e-12) -> np.ndarray:
    denom = float(np.linalg.norm(x) + eps)
    return x / denom


def _checkerboard_rgb(h: int, w: int, block: int = 14) -> np.ndarray:
    y, x = np.indices((h, w))
    pat = ((x // block) + (y // block)) % 2
    c0 = np.array([236, 236, 236], dtype=np.uint8)
    c1 = np.array([214, 214, 214], dtype=np.uint8)
    out = np.empty((h, w, 3), dtype=np.uint8)
    out[pat == 0] = c0
    out[pat == 1] = c1
    return out


class OutfitCompatibilityPipeline:
    def __init__(self, config_path: str | Path) -> None:
        self.cfg = PipelineConfig.from_json(config_path)
        self.data_root = self.cfg.paths.data_root
        self.images_dir = self.data_root / "images"

        if not self.data_root.exists():
            raise FileNotFoundError(f"Data root not found: {self.data_root}")
        if not self.images_dir.exists():
            raise FileNotFoundError(f"Images dir not found: {self.images_dir}")
        if not self.cfg.paths.weights.exists():
            raise FileNotFoundError(f"Weights not found: {self.cfg.paths.weights}")
        self._weights_cache_tag = self._build_weights_cache_tag(self.cfg.paths.weights)
        self._candidate_splits_used = self._effective_candidate_splits()

        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = load_pair_model(
            weights_path=str(self.cfg.paths.weights),
            device=self.device,
            backbone=self.cfg.model.backbone,
            embed_dim=self.cfg.model.embed_dim,
        )
        self.transform = default_transform(self.cfg.model.img_size)

        self.metadata = load_metadata(self.data_root)
        self.category_lookup = load_category_lookup(self.data_root)
        self.type_prior = build_type_prior_map(
            self.data_root,
            cache_path=self.cfg.paths.cache_dir / "type_prior_top_bottom.json",
            alpha=1.0,
        )

        self._candidate_ids: Dict[str, List[str]] = {}
        self._candidate_embs: Dict[str, np.ndarray] = {}
        self._visual_cache: Dict[str, object] = {}
        self._mask_info_cache: Dict[str, MaskResult] = {}
        self._pattern_cache: Dict[str, PatternPrediction] = {}
        self.ollama_explainer = OllamaExplainer(
            cfg=self.cfg.ollama,
            cache_dir=self.cfg.paths.cache_dir,
        )
        self.auto_cropper = AutoBodyCropper(
            cfg=self.cfg.autocrop,
            cache_dir=self.cfg.paths.cache_dir,
        )
        self.segmenter = ForegroundSegmenter(
            cfg=self.cfg.foreground,
            cache_dir=self.cfg.paths.cache_dir,
        )
        self.pattern_predictor: Optional[PatternPredictor] = None
        self.pattern_model_error: str = ""
        p_cfg = self.cfg.pattern_model
        if p_cfg.enabled:
            if p_cfg.weights.exists():
                try:
                    self.pattern_predictor = PatternPredictor(
                        ckpt_path=p_cfg.weights,
                        device=self.device,
                        threshold=p_cfg.threshold,
                    )
                except Exception as exc:  # noqa: BLE001
                    self.pattern_model_error = str(exc)
            else:
                self.pattern_model_error = f"Pattern model not found: {p_cfg.weights}"

        self.category_predictor: Optional[CategoryPredictor] = None
        self.category_model_error: str = ""
        c_cfg = self.cfg.category_model
        if c_cfg.enabled:
            if c_cfg.weights.exists() and c_cfg.mapping.exists():
                try:
                    self.category_predictor = CategoryPredictor(
                        weights_path=c_cfg.weights,
                        mapping_path=c_cfg.mapping,
                        device=self.device,
                        img_size=self.cfg.model.img_size,
                    )
                except Exception as exc:  # noqa: BLE001
                    self.category_model_error = str(exc)
            else:
                missing = []
                if not c_cfg.weights.exists():
                    missing.append(str(c_cfg.weights))
                if not c_cfg.mapping.exists():
                    missing.append(str(c_cfg.mapping))
                self.category_model_error = f"Category model file(s) not found: {', '.join(missing)}"

    def _build_weights_cache_tag(self, weights_path: Path) -> str:
        st = weights_path.stat()
        raw = "|".join(
            [
                str(weights_path.resolve()),
                str(st.st_size),
                str(st.st_mtime_ns),
                self.cfg.model.backbone,
                str(self.cfg.model.embed_dim),
                str(self.cfg.model.img_size),
            ]
        )
        return sha1(raw.encode("utf-8")).hexdigest()[:12]

    def _effective_candidate_splits(self) -> Tuple[str, ...]:
        out: List[str] = []
        allowed = {"train", "valid", "test"}
        for raw in self.cfg.retrieval.candidate_splits:
            split = str(raw).strip().lower()
            if not split or split not in allowed:
                continue
            if split == "test" and not self.cfg.retrieval.allow_test_candidates:
                continue
            if split not in out:
                out.append(split)
        if not out:
            raise RuntimeError(
                "No valid candidate_splits after filtering. "
                "Set retrieval.candidate_splits to include train/valid or enable allow_test_candidates."
            )
        return tuple(out)

    @property
    def foreground_method(self) -> str:
        return self.segmenter.normalized_method()

    def available_foreground_methods(self) -> Tuple[str, ...]:
        return self.segmenter.available_methods()

    def set_foreground_method(self, method: str) -> None:
        self.segmenter.set_method(method)
        self._visual_cache.clear()
        self._mask_info_cache.clear()

    def get_foreground_preview(
        self,
        image_path: str | Path,
        background: Literal["checkerboard", "white", "transparent"] = "checkerboard",
    ) -> Image.Image:
        p = Path(image_path)
        if not p.exists():
            raise FileNotFoundError(f"Image not found: {p}")

        img_bgr = load_bgr(p)
        mask_res = self.segmenter.get_mask(image_path=p, image_bgr=img_bgr)
        rgb = img_bgr[:, :, ::-1].copy()
        m = mask_res.mask.astype(np.float32)[..., np.newaxis]
        alpha = (mask_res.mask.astype(np.uint8) * 255)

        if background == "transparent":
            rgba = np.dstack([rgb, alpha]).astype(np.uint8)
            return Image.fromarray(rgba, mode="RGBA")

        if background == "white":
            bg = np.full_like(rgb, 255, dtype=np.uint8)
        else:
            h, w = rgb.shape[:2]
            bg = _checkerboard_rgb(h=h, w=w, block=14)

        comp = (rgb.astype(np.float32) * m + bg.astype(np.float32) * (1.0 - m)).astype(np.uint8)
        return Image.fromarray(comp, mode="RGB")

    def _load_image_tensor(self, image_path: Path) -> torch.Tensor:
        img = Image.open(image_path).convert("RGB")
        return self.transform(img).unsqueeze(0)

    @torch.no_grad()
    def _encode_image(self, image_path: Path) -> np.ndarray:
        x = self._load_image_tensor(image_path).to(self.device, non_blocking=True)
        emb = self.model.encode(x).detach().cpu().numpy().astype(np.float32)
        return emb[0]

    @torch.no_grad()
    def _model_scores_batch(self, top_embs: np.ndarray, bottom_embs: np.ndarray) -> np.ndarray:
        t = torch.from_numpy(top_embs).to(self.device)
        b = torch.from_numpy(bottom_embs).to(self.device)
        combined = torch.cat([t, b, torch.abs(t - b), t * b], dim=1)
        logits = self.model.head(combined).squeeze(1)
        return torch.sigmoid(logits).detach().cpu().numpy().astype(np.float32)

    def _is_dataset_image_path(self, image_path: Path) -> bool:
        try:
            image_path.resolve().relative_to(self.images_dir.resolve())
            return True
        except Exception:
            return False

    def _prepare_input_path(self, image_path: Path, semantic_hint: str) -> Tuple[Path, AutoCropDecision]:
        if self._is_dataset_image_path(image_path):
            return image_path, AutoCropDecision(
                applied=False,
                reason="dataset_passthrough",
                semantic_hint=semantic_hint,
                method="yolo_pose",
                source_path=str(image_path),
                output_path=str(image_path),
                body_visibility="unknown",
                confidence=0.0,
                crop_box=None,
            )
        return self.auto_cropper.prepare(image_path=image_path, semantic_hint=semantic_hint)

    def _infer_meta_from_path(self, image_path: Path, semantic_hint: str = "") -> _ItemMeta:
        semantic_hint = semantic_hint.strip().lower()
        item_id: Optional[str] = None
        if self._is_dataset_image_path(image_path):
            item_id = infer_item_id_from_path(image_path, self.metadata)
        if item_id is None:
            if self.category_predictor is not None:
                try:
                    img = Image.open(image_path).convert("RGB")
                    preds = self.category_predictor.predict_topk(
                        img=img,
                        topk=max(1, int(self.cfg.category_model.topk)),
                        semantic_hint=semantic_hint,
                    )
                    if preds:
                        min_conf = max(0.0, min(1.0, float(self.cfg.category_model.min_confidence)))
                        chosen = next((p for p in preds if float(p.prob) >= min_conf), None)
                        best = chosen or preds[0]
                        if chosen is None:
                            return _ItemMeta(
                                item_id=None,
                                semantic=semantic_hint,
                                category="",
                                category_name="",
                                text=image_path.stem.lower(),
                                category_source="image_model_low_confidence",
                                category_confidence=float(best.prob),
                            )
                        semantic = semantic_hint or infer_semantic_from_category_name(best.category_name)
                        return _ItemMeta(
                            item_id=None,
                            semantic=semantic,
                            category=str(best.category_id),
                            category_name=best.category_name,
                            text=f"{best.category_name} {image_path.stem}".strip().lower(),
                            category_source="image_model",
                            category_confidence=float(best.prob),
                        )
                except Exception as exc:  # noqa: BLE001
                    self.category_model_error = str(exc)
            return _ItemMeta(
                item_id=None,
                semantic=semantic_hint,
                category="",
                category_name="",
                text=image_path.stem.lower(),
                category_source="none",
                category_confidence=0.0,
            )
        cat = get_item_category(item_id, self.metadata)
        return _ItemMeta(
            item_id=item_id,
            semantic=semantic_category(item_id, self.metadata) or semantic_hint,
            category=cat,
            category_name=self._category_name(cat),
            text=item_text(item_id, self.metadata),
            category_source="metadata",
            category_confidence=1.0,
        )

    def _meta_for_item(self, item_id: str) -> _ItemMeta:
        cat = get_item_category(item_id, self.metadata)
        return _ItemMeta(
            item_id=item_id,
            semantic=semantic_category(item_id, self.metadata),
            category=cat,
            category_name=self._category_name(cat),
            text=item_text(item_id, self.metadata),
            category_source="metadata",
            category_confidence=1.0,
        )

    def _category_name(self, category_id: str) -> str:
        if not category_id:
            return ""
        slot = self.category_lookup.get(str(category_id), {})
        main = str(slot.get("main_category") or "").strip()
        sub = str(slot.get("sub_category") or "").strip()
        if main and sub:
            return f"{main} / {sub}"
        return sub or main or str(category_id)

    def _pattern_cache_key(self, image_path: Path, cache_key: Optional[str] = None) -> str:
        base = cache_key or str(image_path.resolve())
        p_cfg = self.cfg.pattern_model
        ckpt = p_cfg.weights
        ckpt_tag = f"{ckpt.resolve()}:{ckpt.stat().st_mtime_ns}" if ckpt.exists() else str(ckpt)
        raw = f"{base}|{ckpt_tag}|thr={p_cfg.threshold}"
        return sha1(raw.encode("utf-8")).hexdigest()

    def _pattern_for_path(self, image_path: Path, cache_key: Optional[str] = None) -> Optional[PatternPrediction]:
        if self.pattern_predictor is None:
            return None
        key = self._pattern_cache_key(image_path=image_path, cache_key=cache_key)
        if key in self._pattern_cache:
            return self._pattern_cache[key]

        img = Image.open(image_path).convert("RGB")
        pred = self.pattern_predictor.predict(img)
        self._pattern_cache[key] = pred
        return pred

    def _visual_for_path(self, image_path: Path, cache_key: Optional[str] = None, semantic_hint: str = ""):
        key = cache_key or str(image_path.resolve())
        semantic = str(semantic_hint).strip().lower()
        versioned_key = f"{key}|{self.foreground_method}|{int(self.cfg.foreground.enabled)}|{semantic}"
        if versioned_key in self._visual_cache:
            return self._visual_cache[versioned_key], self._mask_info_cache[versioned_key]

        img_bgr = load_bgr(image_path)
        mask_res = self.segmenter.get_mask(image_path=image_path, image_bgr=img_bgr, semantic_hint=semantic)
        feats = extract_visual_features_with_mask(
            img_bgr=img_bgr,
            mask=mask_res.mask,
            ignore_low_sat_bg=self.cfg.foreground.ignore_low_sat_bg,
            low_sat_threshold=self.cfg.foreground.low_sat_threshold,
            near_white_v=self.cfg.foreground.near_white_v,
            near_black_v=self.cfg.foreground.near_black_v,
        )
        self._visual_cache[versioned_key] = feats
        self._mask_info_cache[versioned_key] = mask_res
        return feats, mask_res

    def _shortlist(self, query_emb: np.ndarray, candidate_embs: np.ndarray, top_n: int) -> Tuple[np.ndarray, np.ndarray]:
        if candidate_embs.size == 0:
            return np.zeros((0,), dtype=np.int64), np.zeros((0,), dtype=np.float32)
        qn = _norm_vec(query_emb)
        cn = _norm_rows(candidate_embs)
        sims = (cn @ qn).astype(np.float32)

        k = min(max(1, top_n), sims.shape[0])
        if k == sims.shape[0]:
            idx = np.argsort(-sims)
        else:
            idx = np.argpartition(-sims, k - 1)[:k]
            idx = idx[np.argsort(-sims[idx])]
        return idx.astype(np.int64), sims[idx]

    def _embedding_cache_path(self, semantic: str) -> Path:
        split_tag = "-".join(self._candidate_splits_used)
        fname = (
            f"embeddings_{semantic}_"
            f"{self.cfg.model.backbone}_d{self.cfg.model.embed_dim}_s{self.cfg.model.img_size}_"
            f"{split_tag}_w{self._weights_cache_tag}.npz"
        )
        return self.cfg.paths.cache_dir / fname

    def _ensure_candidates(self, semantic: Literal["tops", "bottoms"]) -> Tuple[List[str], np.ndarray]:
        if semantic in self._candidate_ids and semantic in self._candidate_embs:
            return self._candidate_ids[semantic], self._candidate_embs[semantic]

        item_ids = list_items_by_semantic(
            self.data_root,
            target=semantic,
            splits=self._candidate_splits_used,
        )
        if not item_ids:
            raise RuntimeError(f"No candidate items found for semantic={semantic}")

        cache_path = self._embedding_cache_path(semantic)
        embs: np.ndarray
        cached_ids: List[str]
        if self.cfg.retrieval.embedding_cache and cache_path.exists():
            embs, cached_ids = load_embedding_cache(cache_path)
            item_ids = [str(x) for x in cached_ids]
        else:
            embs, item_ids = build_embeddings(
                model=self.model,
                item_ids=item_ids,
                images_dir=self.images_dir,
                img_size=self.cfg.model.img_size,
                batch_size=self.cfg.retrieval.batch_size,
                device=self.device,
            )
            if self.cfg.retrieval.embedding_cache:
                save_embedding_cache(cache_path, embs, item_ids)

        self._candidate_ids[semantic] = item_ids
        self._candidate_embs[semantic] = embs
        return item_ids, embs

    def _fuse_weights(self, top_meta: _ItemMeta, bottom_meta: _ItemMeta) -> ScoreWeights:
        base = self.cfg.weights.normalized()
        sources = (top_meta.category_source, bottom_meta.category_source)
        if sources[0] == "metadata" and sources[1] == "metadata":
            return base

        penalty = 0.10
        if "image_model_low_confidence" in sources:
            penalty = 0.15

        new_model = max(0.45, base.model - penalty)
        delta = max(0.0, base.model - new_model)
        adjusted = ScoreWeights(
            model=new_model,
            type_prior=base.type_prior,
            color=base.color + 0.5 * delta,
            brightness=base.brightness + 0.3 * delta,
            pattern=base.pattern + 0.2 * delta,
        )
        return adjusted.normalized()

    def _fuse(
        self,
        model_score: float,
        top_meta: _ItemMeta,
        bottom_meta: _ItemMeta,
        top_features,
        bottom_features,
        top_pattern: Optional[PatternPrediction] = None,
        bottom_pattern: Optional[PatternPrediction] = None,
    ) -> Tuple[ScoreBreakdown, Dict[str, object]]:
        top_prior_category = top_meta.category if top_meta.category_source == "metadata" else ""
        bottom_prior_category = bottom_meta.category if bottom_meta.category_source == "metadata" else ""
        tp = type_prior_lookup(
            top_category=top_prior_category,
            bottom_category=bottom_prior_category,
            table=self.type_prior,
            default=0.5,
        )
        color = color_harmony_score(top_features, bottom_features)
        bright = brightness_compat_score(top_features, bottom_features)
        pattern_source = "text_heuristic"
        if top_pattern is not None and bottom_pattern is not None:
            patt = pattern_compat_score_from_predictions(top_pattern, bottom_pattern)
            pattern_source = "image_model"
        else:
            patt = pattern_compat_score(top_meta.text, bottom_meta.text)
        base_weights = self._fuse_weights(top_meta, bottom_meta)
        top_light_rel = float(max(0.0, min(1.0, getattr(top_features, "lighting_reliability", 1.0))))
        bottom_light_rel = float(max(0.0, min(1.0, getattr(bottom_features, "lighting_reliability", 1.0))))
        pair_light_rel = min(top_light_rel, bottom_light_rel)
        color_scale = 0.35 + (0.65 * pair_light_rel)
        brightness_scale = 0.25 + (0.75 * pair_light_rel)
        fuse_weights = ScoreWeights(
            model=base_weights.model,
            type_prior=base_weights.type_prior,
            color=base_weights.color * color_scale,
            brightness=base_weights.brightness * brightness_scale,
            pattern=base_weights.pattern,
        ).normalized()
        top_palette = meaningful_color_palette(top_features.colors, max_colors=3)
        bottom_palette = meaningful_color_palette(bottom_features.colors, max_colors=3)
        score = combine_scores(
            model_score=model_score,
            type_prior_score=tp,
            color_score=color,
            brightness_score=bright,
            pattern_score=patt,
            weights=fuse_weights,
        )
        details = {
            "top_category": top_meta.category_name or top_meta.category,
            "bottom_category": bottom_meta.category_name or bottom_meta.category,
            "top_category_id": top_meta.category,
            "bottom_category_id": bottom_meta.category,
            "top_prior_category_id": top_prior_category,
            "bottom_prior_category_id": bottom_prior_category,
            "top_category_source": top_meta.category_source,
            "bottom_category_source": bottom_meta.category_source,
            "top_category_confidence": float(top_meta.category_confidence),
            "bottom_category_confidence": float(bottom_meta.category_confidence),
            "top_semantic": top_meta.semantic,
            "bottom_semantic": bottom_meta.semantic,
            "top_item_id": top_meta.item_id,
            "bottom_item_id": bottom_meta.item_id,
            "top_primary_color": top_palette[0].name if top_palette else "",
            "bottom_primary_color": bottom_palette[0].name if bottom_palette else "",
            "top_secondary_color": top_palette[1].name if len(top_palette) > 1 else "",
            "bottom_secondary_color": bottom_palette[1].name if len(bottom_palette) > 1 else "",
            "top_color_mode": "dual" if len(top_palette) > 1 else "single",
            "bottom_color_mode": "dual" if len(bottom_palette) > 1 else "single",
            "top_color_palette": [
                {
                    "name": row.name,
                    "pct": float(row.pct),
                    "temperature": row.temperature,
                }
                for row in top_palette
            ],
            "bottom_color_palette": [
                {
                    "name": row.name,
                    "pct": float(row.pct),
                    "temperature": row.temperature,
                }
                for row in bottom_palette
            ],
            "top_mask_coverage": float(top_features.mask_coverage),
            "bottom_mask_coverage": float(bottom_features.mask_coverage),
            "top_effective_mask_coverage": float(top_features.effective_mask_coverage),
            "bottom_effective_mask_coverage": float(bottom_features.effective_mask_coverage),
            "top_lighting_reliability": top_light_rel,
            "bottom_lighting_reliability": bottom_light_rel,
            "pair_lighting_reliability": pair_light_rel,
            "top_white_balance_shift": float(getattr(top_features, "white_balance_shift", 0.0)),
            "bottom_white_balance_shift": float(getattr(bottom_features, "white_balance_shift", 0.0)),
            "foreground_method": self.foreground_method,
            "pattern_source": pattern_source,
            "pattern_model_enabled": bool(self.pattern_predictor is not None),
            "pattern_model_error": self.pattern_model_error,
            "category_model_enabled": bool(self.category_predictor is not None),
            "category_model_error": self.category_model_error,
            "candidate_splits_used": list(self._candidate_splits_used),
            "weights_before_lighting_adjustment": {
                "model": float(base_weights.model),
                "type_prior": float(base_weights.type_prior),
                "color": float(base_weights.color),
                "brightness": float(base_weights.brightness),
                "pattern": float(base_weights.pattern),
            },
            "lighting_weight_adjustment": {
                "color_scale": float(color_scale),
                "brightness_scale": float(brightness_scale),
            },
            "weights_used": {
                "model": float(fuse_weights.model),
                "type_prior": float(fuse_weights.type_prior),
                "color": float(fuse_weights.color),
                "brightness": float(fuse_weights.brightness),
                "pattern": float(fuse_weights.pattern),
            },
        }
        if top_pattern is not None:
            details["top_pattern_label"] = top_pattern.top_label
            details["top_pattern_prob"] = float(top_pattern.top_prob)
            details["top_is_patterned"] = bool(top_pattern.patterned)
        if bottom_pattern is not None:
            details["bottom_pattern_label"] = bottom_pattern.top_label
            details["bottom_pattern_prob"] = float(bottom_pattern.top_prob)
            details["bottom_is_patterned"] = bool(bottom_pattern.patterned)
        return score, details

    def _build_ollama_pair_facts(
        self,
        top_image: Path,
        bottom_image: Path,
        label: str,
        score: ScoreBreakdown,
        details: Dict[str, object],
    ) -> Dict[str, object]:
        top_autocrop = details.get("top_autocrop", {})
        bottom_autocrop = details.get("bottom_autocrop", {})
        return {
            "top_image": str(top_image),
            "bottom_image": str(bottom_image),
            "label": str(label),
            "final_score": float(score.final),
            "breakdown": {
                "model": float(score.model),
                "type_prior": float(score.type_prior),
                "color": float(score.color),
                "brightness": float(score.brightness),
                "pattern": float(score.pattern),
            },
            "thresholds": {
                "weak": float(self.cfg.model.weak_threshold),
                "borderline": float(self.cfg.model.borderline_threshold),
                "good": float(self.cfg.model.threshold),
                "excellent": float(self.cfg.model.excellent_threshold),
            },
            "metadata": {
                "top_category_name": str(details.get("top_category", "")),
                "bottom_category_name": str(details.get("bottom_category", "")),
                "top_primary_color": str(details.get("top_primary_color", "")),
                "bottom_primary_color": str(details.get("bottom_primary_color", "")),
                "top_category_source": str(details.get("top_category_source", "")),
                "bottom_category_source": str(details.get("bottom_category_source", "")),
                "top_mask_fallback": bool(details.get("top_mask_fallback", False)),
                "bottom_mask_fallback": bool(details.get("bottom_mask_fallback", False)),
                "top_autocrop_reason": (
                    str(top_autocrop.get("reason", ""))
                    if isinstance(top_autocrop, dict)
                    else ""
                ),
                "bottom_autocrop_reason": (
                    str(bottom_autocrop.get("reason", ""))
                    if isinstance(bottom_autocrop, dict)
                    else ""
                ),
            },
        }

    def _attach_ollama_pair_explanation(
        self,
        top_image: Path,
        bottom_image: Path,
        label: str,
        score: ScoreBreakdown,
        details: Dict[str, object],
    ) -> None:
        facts = self._build_ollama_pair_facts(
            top_image=top_image,
            bottom_image=bottom_image,
            label=label,
            score=score,
            details=details,
        )
        llm = self.ollama_explainer.explain(facts=facts)
        details["llm_status"] = llm.status
        details["llm_cached"] = bool(llm.cached)
        if llm.explanation is not None:
            details["llm_explanation"] = llm.explanation
        if llm.status != "ok" and llm.raw:
            details["llm_raw"] = llm.raw
        if llm.error:
            details["llm_error"] = llm.error

    def _build_ollama_retrieval_facts(
        self,
        mode: RetrievalMode,
        query_image: Path,
        row: RankedCandidate,
    ) -> Dict[str, object]:
        d = row.details if isinstance(row.details, dict) else {}
        query_autocrop = d.get("query_autocrop", {})
        return {
            "mode": str(mode),
            "query_image": str(query_image),
            "candidate_image": str(row.image_path),
            "candidate_item_id": str(row.item_id),
            "rank": int(row.rank),
            "label": label_from_score(
                row.score.final,
                threshold=self.cfg.model.threshold,
                borderline_threshold=self.cfg.model.borderline_threshold,
                weak_threshold=self.cfg.model.weak_threshold,
                excellent_threshold=self.cfg.model.excellent_threshold,
            ),
            "final_score": float(row.score.final),
            "breakdown": {
                "model": float(row.score.model),
                "type_prior": float(row.score.type_prior),
                "color": float(row.score.color),
                "brightness": float(row.score.brightness),
                "pattern": float(row.score.pattern),
                "cosine_shortlist_score": float(d.get("cosine_shortlist_score", 0.0)),
            },
            "thresholds": {
                "weak": float(self.cfg.model.weak_threshold),
                "borderline": float(self.cfg.model.borderline_threshold),
                "good": float(self.cfg.model.threshold),
                "excellent": float(self.cfg.model.excellent_threshold),
            },
            "metadata": {
                "query_category_name": str(d.get("query_category_name", "")),
                "candidate_category_name": str(d.get("candidate_category_name", "")),
                "top_category_name": str(d.get("top_category", "")),
                "bottom_category_name": str(d.get("bottom_category", "")),
                "top_primary_color": str(d.get("top_primary_color", "")),
                "bottom_primary_color": str(d.get("bottom_primary_color", "")),
                "query_category_source": str(d.get("query_category_source", "")),
                "candidate_category_source": str(d.get("candidate_category_source", "")),
                "query_mask_fallback": bool(d.get("query_mask_fallback", False)),
                "candidate_mask_fallback": bool(d.get("candidate_mask_fallback", False)),
                "query_autocrop_reason": (
                    str(query_autocrop.get("reason", ""))
                    if isinstance(query_autocrop, dict)
                    else ""
                ),
            },
        }

    def _attach_ollama_retrieval_explanation(
        self,
        mode: RetrievalMode,
        query_image: Path,
        row: RankedCandidate,
    ) -> None:
        facts = self._build_ollama_retrieval_facts(
            mode=mode,
            query_image=query_image,
            row=row,
        )
        llm = self.ollama_explainer.explain(facts=facts)
        row.details["llm_status"] = llm.status
        row.details["llm_cached"] = bool(llm.cached)
        if llm.explanation is not None:
            row.details["llm_explanation"] = llm.explanation
        if llm.status != "ok" and llm.raw:
            row.details["llm_raw"] = llm.raw
        if llm.error:
            row.details["llm_error"] = llm.error

    def score_pair(
        self,
        top_image: str | Path,
        bottom_image: str | Path,
        include_llm: bool = True,
    ) -> PairResult:
        top_input_path = Path(top_image)
        bottom_input_path = Path(bottom_image)
        if not top_input_path.exists():
            raise FileNotFoundError(f"Top image not found: {top_input_path}")
        if not bottom_input_path.exists():
            raise FileNotFoundError(f"Bottom image not found: {bottom_input_path}")

        top_path, top_crop = self._prepare_input_path(top_input_path, semantic_hint="tops")
        bottom_path, bottom_crop = self._prepare_input_path(bottom_input_path, semantic_hint="bottoms")

        top_meta = self._infer_meta_from_path(top_path, semantic_hint="tops")
        bottom_meta = self._infer_meta_from_path(bottom_path, semantic_hint="bottoms")

        top_emb = self._encode_image(top_path)
        bottom_emb = self._encode_image(bottom_path)
        model_score = float(
            self._model_scores_batch(top_emb[np.newaxis, :], bottom_emb[np.newaxis, :])[0]
        )

        top_vis, top_mask = self._visual_for_path(
            top_path,
            cache_key=top_meta.item_id or str(top_path),
            semantic_hint="tops",
        )
        bottom_vis, bottom_mask = self._visual_for_path(
            bottom_path,
            cache_key=bottom_meta.item_id or str(bottom_path),
            semantic_hint="bottoms",
        )
        top_pat = self._pattern_for_path(top_path, cache_key=top_meta.item_id or str(top_path))
        bottom_pat = self._pattern_for_path(bottom_path, cache_key=bottom_meta.item_id or str(bottom_path))
        score, details = self._fuse(
            model_score=model_score,
            top_meta=top_meta,
            bottom_meta=bottom_meta,
            top_features=top_vis,
            bottom_features=bottom_vis,
            top_pattern=top_pat,
            bottom_pattern=bottom_pat,
        )
        details["top_mask_fallback"] = bool(top_mask.used_fallback)
        details["bottom_mask_fallback"] = bool(bottom_mask.used_fallback)
        details["top_autocrop"] = {
            "applied": bool(top_crop.applied),
            "reason": top_crop.reason,
            "processed_path": str(top_path),
            "body_visibility": top_crop.body_visibility,
            "confidence": float(top_crop.confidence),
            "crop_box": list(top_crop.crop_box) if top_crop.crop_box else None,
            "error": top_crop.error,
        }
        details["bottom_autocrop"] = {
            "applied": bool(bottom_crop.applied),
            "reason": bottom_crop.reason,
            "processed_path": str(bottom_path),
            "body_visibility": bottom_crop.body_visibility,
            "confidence": float(bottom_crop.confidence),
            "crop_box": list(bottom_crop.crop_box) if bottom_crop.crop_box else None,
            "error": bottom_crop.error,
        }
        details["autocrop_model_error"] = self.auto_cropper.model_error
        details["threshold"] = float(self.cfg.model.threshold)
        details["good_threshold"] = float(self.cfg.model.threshold)
        details["borderline_threshold"] = float(self.cfg.model.borderline_threshold)
        details["weak_threshold"] = float(self.cfg.model.weak_threshold)
        details["excellent_threshold"] = float(self.cfg.model.excellent_threshold)
        label = label_from_score(
            score.final,
            threshold=self.cfg.model.threshold,
            borderline_threshold=self.cfg.model.borderline_threshold,
            weak_threshold=self.cfg.model.weak_threshold,
            excellent_threshold=self.cfg.model.excellent_threshold,
        )
        if include_llm:
            self._attach_ollama_pair_explanation(
                top_image=top_input_path,
                bottom_image=bottom_input_path,
                label=label,
                score=score,
                details=details,
            )
        else:
            details["llm_status"] = "deferred"
            details["llm_cached"] = False

        return PairResult(
            top_image=str(top_input_path),
            bottom_image=str(bottom_input_path),
            score=score,
            label=label,
            details=details,
        )

    def rank(
        self,
        mode: RetrievalMode,
        query_image: str | Path,
        top_k: Optional[int] = None,
        shortlist_k: Optional[int] = None,
        include_llm: bool = True,
    ) -> List[RankedCandidate]:
        if mode not in ("top2bottom", "bottom2top"):
            raise ValueError(f"Unsupported mode: {mode}")

        query_input_path = Path(query_image)
        if not query_input_path.exists():
            raise FileNotFoundError(f"Query image not found: {query_input_path}")

        if mode == "top2bottom":
            candidate_semantic: Literal["tops", "bottoms"] = "bottoms"
            query_is_top = True
            query_semantic_hint = "tops"
        else:
            candidate_semantic = "tops"
            query_is_top = False
            query_semantic_hint = "bottoms"

        query_path, query_crop = self._prepare_input_path(query_input_path, semantic_hint=query_semantic_hint)
        q_meta = self._infer_meta_from_path(query_path, semantic_hint=query_semantic_hint)
        q_emb = self._encode_image(query_path)
        q_vis, q_mask = self._visual_for_path(
            query_path,
            cache_key=q_meta.item_id or str(query_path),
            semantic_hint=query_semantic_hint,
        )
        q_pat = self._pattern_for_path(query_path, cache_key=q_meta.item_id or str(query_path))

        candidate_ids, candidate_embs = self._ensure_candidates(candidate_semantic)
        shortlist = int(shortlist_k or self.cfg.retrieval.shortlist_k)
        idx, cos_vals = self._shortlist(q_emb, candidate_embs, top_n=shortlist)
        if idx.size == 0:
            return []

        short_ids = [candidate_ids[int(i)] for i in idx.tolist()]
        short_embs = candidate_embs[idx]

        if query_is_top:
            top_embs = np.repeat(q_emb[np.newaxis, :], short_embs.shape[0], axis=0)
            bottom_embs = short_embs
        else:
            top_embs = short_embs
            bottom_embs = np.repeat(q_emb[np.newaxis, :], short_embs.shape[0], axis=0)

        model_scores = self._model_scores_batch(top_embs, bottom_embs)
        rows: List[RankedCandidate] = []

        for i, candidate_id in enumerate(short_ids):
            c_path = self.images_dir / f"{candidate_id}.jpg"
            c_meta = self._meta_for_item(candidate_id)
            c_vis, c_mask = self._visual_for_path(
                c_path,
                cache_key=candidate_id,
                semantic_hint=candidate_semantic,
            )
            c_pat = self._pattern_for_path(c_path, cache_key=candidate_id)

            if query_is_top:
                top_meta, bottom_meta = q_meta, c_meta
                top_vis, bottom_vis = q_vis, c_vis
                top_pat, bottom_pat = q_pat, c_pat
            else:
                top_meta, bottom_meta = c_meta, q_meta
                top_vis, bottom_vis = c_vis, q_vis
                top_pat, bottom_pat = c_pat, q_pat

            score, details = self._fuse(
                model_score=float(model_scores[i]),
                top_meta=top_meta,
                bottom_meta=bottom_meta,
                top_features=top_vis,
                bottom_features=bottom_vis,
                top_pattern=top_pat,
                bottom_pattern=bottom_pat,
            )
            details["cosine_shortlist_score"] = float(cos_vals[i])
            details["query_item_id"] = q_meta.item_id
            details["query_semantic"] = q_meta.semantic
            details["query_category"] = q_meta.category
            details["query_category_name"] = q_meta.category_name or q_meta.category
            details["query_category_source"] = q_meta.category_source
            details["query_category_confidence"] = float(q_meta.category_confidence)
            details["query_autocrop"] = {
                "applied": bool(query_crop.applied),
                "reason": query_crop.reason,
                "processed_path": str(query_path),
                "body_visibility": query_crop.body_visibility,
                "confidence": float(query_crop.confidence),
                "crop_box": list(query_crop.crop_box) if query_crop.crop_box else None,
                "error": query_crop.error,
            }
            details["autocrop_model_error"] = self.auto_cropper.model_error
            details["candidate_category"] = c_meta.category
            details["candidate_category_name"] = c_meta.category_name or c_meta.category
            details["candidate_category_source"] = c_meta.category_source
            details["candidate_category_confidence"] = float(c_meta.category_confidence)
            details["query_mask_fallback"] = bool(q_mask.used_fallback)
            details["candidate_mask_fallback"] = bool(c_mask.used_fallback)

            rows.append(
                RankedCandidate(
                    rank=-1,
                    item_id=candidate_id,
                    image_path=str(c_path),
                    semantic_category=c_meta.semantic,
                    score=score,
                    details=details,
                )
            )

        rows.sort(key=lambda x: x.score.final, reverse=True)
        k = min(int(top_k or self.cfg.retrieval.top_k), len(rows))
        out = rows[:k]
        for rank_i, row in enumerate(out, start=1):
            row.rank = rank_i
        if out:
            if include_llm:
                self._attach_ollama_retrieval_explanation(
                    mode=mode,
                    query_image=query_input_path,
                    row=out[0],
                )
            else:
                out[0].details["llm_status"] = "deferred"
                out[0].details["llm_cached"] = False
        return out

    def rank_top_to_bottom(
        self,
        query_top_image: str | Path,
        top_k: Optional[int] = None,
        shortlist_k: Optional[int] = None,
        include_llm: bool = True,
    ) -> List[RankedCandidate]:
        return self.rank(
            mode="top2bottom",
            query_image=query_top_image,
            top_k=top_k,
            shortlist_k=shortlist_k,
            include_llm=include_llm,
        )

    def rank_bottom_to_top(
        self,
        query_bottom_image: str | Path,
        top_k: Optional[int] = None,
        shortlist_k: Optional[int] = None,
        include_llm: bool = True,
    ) -> List[RankedCandidate]:
        return self.rank(
            mode="bottom2top",
            query_image=query_bottom_image,
            top_k=top_k,
            shortlist_k=shortlist_k,
            include_llm=include_llm,
        )
