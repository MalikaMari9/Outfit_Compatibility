from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha1
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
import torch

from .config import ForegroundConfig


@dataclass
class MaskResult:
    mask: np.ndarray
    method: str
    coverage: float
    used_fallback: bool


def _as_bool_mask(mask: np.ndarray) -> np.ndarray:
    if mask.dtype == np.bool_:
        return mask
    return mask.astype(np.uint8) > 0


def _largest_component(mask: np.ndarray) -> np.ndarray:
    m = (mask.astype(np.uint8) > 0).astype(np.uint8)
    if m.sum() == 0:
        return m.astype(bool)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    if n <= 2:
        return m.astype(bool)
    areas = stats[1:, cv2.CC_STAT_AREA]
    largest = int(1 + np.argmax(areas))
    return (labels == largest)


def _smooth_mask(mask: np.ndarray) -> np.ndarray:
    m = (mask.astype(np.uint8) > 0).astype(np.uint8) * 255
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, k)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, k)
    return (m > 0)


class ForegroundSegmenter:
    METHOD_ALIASES: Dict[str, str] = {
        "none": "none",
        "off": "none",
        "rembg": "rembg",
        "u2": "u2net",
        "u2net": "u2net",
        "u2netp": "u2netp",
        "isnet": "isnet",
        "segformer": "segformer",
    }

    def __init__(self, cfg: ForegroundConfig, cache_dir: Path) -> None:
        self.cfg = cfg
        self.cache_dir = cache_dir / "masks"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self._rembg_sessions: Dict[str, object] = {}
        self._segformer_processor = None
        self._segformer_model = None
        self._segformer_target_ids: Optional[List[int]] = None
        self._segformer_device = torch.device("cpu")

    @classmethod
    def available_methods(cls) -> Tuple[str, ...]:
        return ("none", "rembg", "u2net", "u2netp", "isnet", "segformer")

    def normalized_method(self) -> str:
        key = str(self.cfg.method).strip().lower()
        return self.METHOD_ALIASES.get(key, key)

    def set_method(self, method: str) -> None:
        self.cfg.method = method

    def _cache_key(self, image_path: Path, method: str) -> str:
        st = image_path.stat()
        payload = "|".join(
            [
                str(image_path.resolve()),
                str(st.st_mtime_ns),
                str(st.st_size),
                method,
                str(self.cfg.alpha_threshold),
                str(self.cfg.min_mask_ratio),
                str(self.cfg.segformer_model_id),
                ",".join(self.cfg.segformer_target_labels),
            ]
        )
        return sha1(payload.encode("utf-8")).hexdigest()

    def _cache_path(self, image_path: Path, method: str) -> Path:
        return self.cache_dir / method / f"{self._cache_key(image_path, method)}.npz"

    def _read_cache(self, path: Path) -> Optional[MaskResult]:
        if not path.exists():
            return None
        data = np.load(path, allow_pickle=False)
        mask = data["mask"].astype(np.uint8) > 0
        coverage = float(data["coverage"][0])
        used_fallback = bool(int(data["used_fallback"][0]))
        method = str(data["method"][0])
        return MaskResult(mask=mask, method=method, coverage=coverage, used_fallback=used_fallback)

    def _write_cache(self, path: Path, res: MaskResult) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            path,
            mask=res.mask.astype(np.uint8),
            coverage=np.array([res.coverage], dtype=np.float32),
            used_fallback=np.array([1 if res.used_fallback else 0], dtype=np.int8),
            method=np.array([res.method], dtype="<U32"),
        )

    def _fallback_full_mask(self, h: int, w: int, method: str) -> MaskResult:
        mask = np.ones((h, w), dtype=bool)
        return MaskResult(mask=mask, method=method, coverage=1.0, used_fallback=True)

    def _validate_or_fallback(self, mask: np.ndarray, method: str) -> MaskResult:
        m = _as_bool_mask(mask)
        if m.ndim != 2:
            raise ValueError(f"Expected 2D mask, got shape={m.shape}")
        m = _smooth_mask(m)
        m = _largest_component(m)
        coverage = float(m.mean()) if m.size else 0.0
        if coverage < float(self.cfg.min_mask_ratio):
            return self._fallback_full_mask(m.shape[0], m.shape[1], method=method)
        return MaskResult(mask=m, method=method, coverage=coverage, used_fallback=False)

    def _extract_mask_rembg(self, image_path: Path, model_name: Optional[str]) -> np.ndarray:
        try:
            from rembg import new_session, remove
        except Exception as exc:
            raise RuntimeError(
                "rembg backend requested but rembg is not importable. Install: pip install rembg onnxruntime"
            ) from exc

        session = None
        if model_name:
            session = self._rembg_sessions.get(model_name)
            if session is None:
                session = new_session(model_name=model_name)
                self._rembg_sessions[model_name] = session

        input_bytes = image_path.read_bytes()
        output_bytes = remove(input_bytes, session=session) if session is not None else remove(input_bytes)
        arr = cv2.imdecode(np.frombuffer(output_bytes, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
        if arr is None:
            raise RuntimeError(f"rembg failed to decode output for image: {image_path}")

        if arr.ndim == 3 and arr.shape[2] == 4:
            alpha = arr[:, :, 3]
            return alpha >= int(self.cfg.alpha_threshold)

        if arr.ndim == 3:
            gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
        else:
            gray = arr
        # Conservative fallback if alpha is unavailable.
        return gray > 0

    def _resolve_segformer_targets(self, id2label: Dict[int, str], targets: Tuple[str, ...]) -> List[int]:
        tks = [x.strip().lower() for x in targets if str(x).strip()]
        target_ids: List[int] = []
        for idx, label in id2label.items():
            low = str(label).lower()
            if any(tok in low for tok in tks):
                target_ids.append(int(idx))
        return sorted(set(target_ids))

    def _load_segformer(self) -> None:
        if self._segformer_model is not None and self._segformer_processor is not None:
            return

        try:
            from transformers import AutoImageProcessor, AutoModelForSemanticSegmentation
        except Exception as exc:
            raise RuntimeError(
                "segformer backend requested but transformers is not importable. Install: pip install transformers"
            ) from exc

        model_id = self.cfg.segformer_model_id
        os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
        self._segformer_processor = AutoImageProcessor.from_pretrained(model_id)
        self._segformer_model = AutoModelForSemanticSegmentation.from_pretrained(model_id)

        if self.cfg.segformer_device == "cuda" and torch.cuda.is_available():
            self._segformer_device = torch.device("cuda")
        elif self.cfg.segformer_device == "cpu":
            self._segformer_device = torch.device("cpu")
        else:
            self._segformer_device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        self._segformer_model.to(self._segformer_device)
        self._segformer_model.eval()

        id2label = getattr(self._segformer_model.config, "id2label", {}) or {}
        id2label = {int(k): str(v) for k, v in id2label.items()}
        target_ids = self._resolve_segformer_targets(id2label, self.cfg.segformer_target_labels)
        if not target_ids:
            known = ", ".join(f"{k}:{v}" for k, v in sorted(id2label.items())[:30])
            raise RuntimeError(
                "No segformer target labels matched model id2label. "
                f"model={self.cfg.segformer_model_id}; check segformer_target_labels. "
                f"Known labels sample: {known}"
            )
        self._segformer_target_ids = target_ids

    def _extract_mask_segformer(self, image_bgr: np.ndarray) -> np.ndarray:
        self._load_segformer()
        assert self._segformer_processor is not None
        assert self._segformer_model is not None
        assert self._segformer_target_ids is not None

        rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        inputs = self._segformer_processor(images=rgb, return_tensors="pt")
        inputs = {k: v.to(self._segformer_device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = self._segformer_model(**inputs)
            logits = outputs.logits
            up = torch.nn.functional.interpolate(
                logits,
                size=rgb.shape[:2],
                mode="bilinear",
                align_corners=False,
            )
            pred = up.argmax(dim=1)[0].detach().cpu().numpy()

        return np.isin(pred, self._segformer_target_ids)

    def get_mask(self, image_path: Path, image_bgr: Optional[np.ndarray] = None) -> MaskResult:
        if image_bgr is None:
            image_bgr = cv2.imread(str(image_path))
            if image_bgr is None:
                raise FileNotFoundError(f"Failed to read image: {image_path}")

        method = self.normalized_method()
        if not self.cfg.enabled or method == "none":
            return MaskResult(
                mask=np.ones(image_bgr.shape[:2], dtype=bool),
                method="none",
                coverage=1.0,
                used_fallback=False,
            )

        cache_path = self._cache_path(image_path, method)
        if self.cfg.cache_masks:
            cached = self._read_cache(cache_path)
            if cached is not None:
                return cached

        if method == "rembg":
            raw = self._extract_mask_rembg(image_path, model_name=None)
        elif method == "u2net":
            raw = self._extract_mask_rembg(image_path, model_name="u2net")
        elif method == "u2netp":
            raw = self._extract_mask_rembg(image_path, model_name="u2netp")
        elif method == "isnet":
            raw = self._extract_mask_rembg(image_path, model_name="isnet-general-use")
        elif method == "segformer":
            raw = self._extract_mask_segformer(image_bgr)
        else:
            raise ValueError(
                f"Unsupported foreground method: {method}. "
                f"Available: {', '.join(self.available_methods())}"
            )

        result = self._validate_or_fallback(raw, method=method)
        if self.cfg.cache_masks:
            self._write_cache(cache_path, result)
        return result
