from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha1
import json
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np

from .config import AutoCropConfig


@dataclass
class AutoCropDecision:
    applied: bool
    reason: str
    semantic_hint: str
    method: str
    source_path: str
    output_path: str
    body_visibility: str
    confidence: float
    crop_box: Optional[Tuple[int, int, int, int]]
    error: str = ""


class AutoBodyCropper:
    def __init__(self, cfg: AutoCropConfig, cache_dir: Path) -> None:
        self.cfg = cfg
        self.cache_dir = cache_dir / "autocrop"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._model = None
        self._model_error = ""

    @property
    def model_error(self) -> str:
        return self._model_error

    def _weights_tag(self) -> str:
        w = self.cfg.weights
        if w.exists():
            st = w.stat()
            return f"{w.resolve()}:{st.st_size}:{st.st_mtime_ns}"
        return str(w)

    def _cache_key(self, image_path: Path, semantic_hint: str) -> str:
        st = image_path.stat()
        payload = "|".join(
            [
                str(image_path.resolve()),
                str(st.st_size),
                str(st.st_mtime_ns),
                semantic_hint,
                str(self.cfg.conf),
                str(self.cfg.keypoint_conf),
                str(self.cfg.pad_ratio),
                str(self.cfg.shoe_cut),
                str(self.cfg.min_person_box_ratio),
                str(self.cfg.min_crop_area_ratio),
                str(self.cfg.full_body_tighten_ratio),
                "full_body_tighten_algo_v2",
                self._weights_tag(),
            ]
        )
        return sha1(payload.encode("utf-8")).hexdigest()

    def _cache_paths(self, key: str) -> Tuple[Path, Path]:
        img_path = self.cache_dir / f"{key}.jpg"
        meta_path = self.cache_dir / f"{key}.json"
        return img_path, meta_path

    def _load_model(self) -> bool:
        if self._model is not None:
            return True
        if self._model_error:
            return False
        if not self.cfg.weights.exists():
            self._model_error = f"Pose weights not found: {self.cfg.weights}"
            return False
        try:
            from ultralytics import YOLO
        except Exception as exc:  # noqa: BLE001
            self._model_error = (
                "ultralytics import failed. Install with: pip install ultralytics. "
                f"Error: {exc}"
            )
            return False
        try:
            self._model = YOLO(str(self.cfg.weights))
            return True
        except Exception as exc:  # noqa: BLE001
            self._model_error = f"Failed to load YOLO pose model: {exc}"
            return False

    def _read_meta(self, meta_path: Path) -> Optional[dict]:
        if not meta_path.exists():
            return None
        try:
            return json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _write_meta(self, meta_path: Path, payload: dict) -> None:
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(json.dumps(payload), encoding="utf-8")

    def _clip_box(self, x1: float, y1: float, x2: float, y2: float, w: int, h: int) -> Tuple[int, int, int, int]:
        xx1 = int(max(0, min(round(x1), w - 1)))
        yy1 = int(max(0, min(round(y1), h - 1)))
        xx2 = int(max(0, min(round(x2), w)))
        yy2 = int(max(0, min(round(y2), h)))
        if xx2 <= xx1:
            xx2 = min(w, xx1 + 1)
        if yy2 <= yy1:
            yy2 = min(h, yy1 + 1)
        return xx1, yy1, xx2, yy2

    def _adaptive_full_body_tighten_ratio(self, person_area_ratio: float, anchor_count: int) -> float:
        base = max(0.0, min(float(self.cfg.full_body_tighten_ratio), 0.22))
        if base <= 0.0:
            return 0.0

        scale = 1.0
        if person_area_ratio < 0.16:
            scale = 1.45
        elif person_area_ratio < 0.28:
            scale = 1.15
        elif person_area_ratio > 0.48:
            scale = 0.55
        elif person_area_ratio > 0.38:
            scale = 0.75

        if anchor_count <= 1:
            scale *= 0.45
        elif anchor_count == 2:
            scale *= 0.70
        elif anchor_count >= 4:
            scale *= 1.05

        return max(0.0, min(base * scale, 0.22))

    def _semantic_anchor_points(
        self,
        semantic: str,
        shoulders: List[Tuple[float, float]],
        hips: List[Tuple[float, float]],
        knees: List[Tuple[float, float]],
        ankles: List[Tuple[float, float]],
    ) -> List[Tuple[float, float]]:
        if semantic == "tops":
            return [*shoulders, *hips]
        return [*hips, *knees, *ankles]

    def _tighten_full_body_box(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        *,
        semantic: str,
        visibility: str,
        person_area_ratio: float,
        shoulders: List[Tuple[float, float]],
        hips: List[Tuple[float, float]],
        knees: List[Tuple[float, float]],
        ankles: List[Tuple[float, float]],
        w: int,
        h: int,
    ) -> Tuple[int, int, int, int]:
        if visibility != "full_body":
            return x1, y1, x2, y2

        anchor_points = self._semantic_anchor_points(semantic, shoulders, hips, knees, ankles)
        tighten_ratio = self._adaptive_full_body_tighten_ratio(person_area_ratio, len(anchor_points))
        if tighten_ratio <= 0.0:
            return x1, y1, x2, y2

        box_w = max(1, x2 - x1)
        box_h = max(1, y2 - y1)
        tx1 = float(x1)
        tx2 = float(x2)
        if len(anchor_points) >= 2:
            xs = [float(p[0]) for p in anchor_points]
            span = max(xs) - min(xs)
            if span > 1.0:
                center_x = (min(xs) + max(xs)) * 0.5
                anchor_pad = 0.30 if semantic == "tops" else 0.24
                min_w_from_points = span * (1.0 + anchor_pad)
                desired_w = box_w * max(0.60, 1.0 - (tighten_ratio * 1.35))
                target_w = min(float(box_w), max(min_w_from_points, desired_w))
                half_w = max(1.0, target_w * 0.5)
                tx1 = center_x - half_w
                tx2 = center_x + half_w
        if tx1 == float(x1) and tx2 == float(x2):
            trim_x = box_w * tighten_ratio * 0.5
            tx1 = float(x1) + trim_x
            tx2 = float(x2) - trim_x

        if semantic == "tops":
            trim_top = box_h * tighten_ratio * 0.08
            trim_bottom = box_h * tighten_ratio * 0.92
        else:
            trim_top = box_h * tighten_ratio * 0.92
            trim_bottom = box_h * tighten_ratio * 0.08
        ty1 = float(y1) + trim_top
        ty2 = float(y2) - trim_bottom

        tightened = self._clip_box(tx1, ty1, tx2, ty2, w=w, h=h)
        area_ratio = float(
            max(0, tightened[2] - tightened[0]) * max(0, tightened[3] - tightened[1]) / max(1.0, float(h * w))
        )
        if area_ratio < float(self.cfg.min_crop_area_ratio):
            return x1, y1, x2, y2
        return tightened

    def _kp(
        self,
        kxy: np.ndarray,
        kconf: Optional[np.ndarray],
        idx: int,
    ) -> Optional[Tuple[float, float]]:
        if idx < 0 or idx >= kxy.shape[0]:
            return None
        x = float(kxy[idx, 0])
        y = float(kxy[idx, 1])
        if not np.isfinite(x) or not np.isfinite(y):
            return None
        if x <= 1.0 and y <= 1.0:
            return None
        if kconf is not None:
            conf = float(kconf[idx])
            if conf < float(self.cfg.keypoint_conf):
                return None
        return x, y

    def _visibility(
        self,
        shoulders: List[Tuple[float, float]],
        hips: List[Tuple[float, float]],
        knees: List[Tuple[float, float]],
        ankles: List[Tuple[float, float]],
    ) -> str:
        has_sh = bool(shoulders)
        has_hp = bool(hips)
        has_kn = bool(knees)
        has_an = bool(ankles)
        if has_sh and has_hp and (has_kn or has_an):
            return "full_body"
        if has_sh and has_hp:
            return "upper_body"
        if has_hp and (has_kn or has_an):
            return "mid_lower"
        if has_sh:
            return "upper_partial"
        if has_kn or has_an:
            return "lower_partial"
        return "unknown"

    def prepare(self, image_path: Path, semantic_hint: str) -> Tuple[Path, AutoCropDecision]:
        semantic = str(semantic_hint).strip().lower()
        if not self.cfg.enabled:
            return image_path, AutoCropDecision(
                applied=False,
                reason="disabled",
                semantic_hint=semantic,
                method="yolo_pose",
                source_path=str(image_path),
                output_path=str(image_path),
                body_visibility="unknown",
                confidence=0.0,
                crop_box=None,
            )

        if semantic not in {"tops", "bottoms"}:
            return image_path, AutoCropDecision(
                applied=False,
                reason="unsupported_semantic",
                semantic_hint=semantic,
                method="yolo_pose",
                source_path=str(image_path),
                output_path=str(image_path),
                body_visibility="unknown",
                confidence=0.0,
                crop_box=None,
            )

        if not image_path.exists():
            return image_path, AutoCropDecision(
                applied=False,
                reason="image_missing",
                semantic_hint=semantic,
                method="yolo_pose",
                source_path=str(image_path),
                output_path=str(image_path),
                body_visibility="unknown",
                confidence=0.0,
                crop_box=None,
            )

        key = self._cache_key(image_path, semantic)
        cache_img, cache_meta = self._cache_paths(key)
        if self.cfg.cache_crops:
            cached = self._read_meta(cache_meta)
            if isinstance(cached, dict):
                if bool(cached.get("applied", False)) and cache_img.exists():
                    return cache_img, AutoCropDecision(
                        applied=True,
                        reason=str(cached.get("reason", "cache_hit")),
                        semantic_hint=semantic,
                        method="yolo_pose",
                        source_path=str(image_path),
                        output_path=str(cache_img),
                        body_visibility=str(cached.get("body_visibility", "unknown")),
                        confidence=float(cached.get("confidence", 0.0)),
                        crop_box=tuple(cached.get("crop_box")) if cached.get("crop_box") else None,
                        error=str(cached.get("error", "")),
                    )
                if not bool(cached.get("applied", False)):
                    return image_path, AutoCropDecision(
                        applied=False,
                        reason=str(cached.get("reason", "cache_skip")),
                        semantic_hint=semantic,
                        method="yolo_pose",
                        source_path=str(image_path),
                        output_path=str(image_path),
                        body_visibility=str(cached.get("body_visibility", "unknown")),
                        confidence=float(cached.get("confidence", 0.0)),
                        crop_box=tuple(cached.get("crop_box")) if cached.get("crop_box") else None,
                        error=str(cached.get("error", "")),
                    )

        if not self._load_model():
            decision = AutoCropDecision(
                applied=False,
                reason="model_unavailable",
                semantic_hint=semantic,
                method="yolo_pose",
                source_path=str(image_path),
                output_path=str(image_path),
                body_visibility="unknown",
                confidence=0.0,
                crop_box=None,
                error=self._model_error,
            )
            return image_path, decision

        img_bgr = cv2.imread(str(image_path))
        if img_bgr is None:
            decision = AutoCropDecision(
                applied=False,
                reason="image_read_failed",
                semantic_hint=semantic,
                method="yolo_pose",
                source_path=str(image_path),
                output_path=str(image_path),
                body_visibility="unknown",
                confidence=0.0,
                crop_box=None,
            )
            if self.cfg.cache_crops:
                self._write_meta(cache_meta, asdict(decision))
            return image_path, decision

        h, w = img_bgr.shape[:2]
        try:
            results = self._model.predict(img_bgr, conf=float(self.cfg.conf), verbose=False)
        except Exception as exc:  # noqa: BLE001
            decision = AutoCropDecision(
                applied=False,
                reason="pose_predict_failed",
                semantic_hint=semantic,
                method="yolo_pose",
                source_path=str(image_path),
                output_path=str(image_path),
                body_visibility="unknown",
                confidence=0.0,
                crop_box=None,
                error=str(exc),
            )
            if self.cfg.cache_crops:
                self._write_meta(cache_meta, asdict(decision))
            return image_path, decision

        if not results:
            decision = AutoCropDecision(
                applied=False,
                reason="no_detections",
                semantic_hint=semantic,
                method="yolo_pose",
                source_path=str(image_path),
                output_path=str(image_path),
                body_visibility="unknown",
                confidence=0.0,
                crop_box=None,
            )
            if self.cfg.cache_crops:
                self._write_meta(cache_meta, asdict(decision))
            return image_path, decision

        r0 = results[0]
        if getattr(r0, "boxes", None) is None or getattr(r0, "keypoints", None) is None:
            decision = AutoCropDecision(
                applied=False,
                reason="missing_boxes_or_keypoints",
                semantic_hint=semantic,
                method="yolo_pose",
                source_path=str(image_path),
                output_path=str(image_path),
                body_visibility="unknown",
                confidence=0.0,
                crop_box=None,
            )
            if self.cfg.cache_crops:
                self._write_meta(cache_meta, asdict(decision))
            return image_path, decision

        boxes_xyxy = r0.boxes.xyxy.cpu().numpy() if r0.boxes.xyxy is not None else np.zeros((0, 4))
        if boxes_xyxy.shape[0] == 0:
            decision = AutoCropDecision(
                applied=False,
                reason="empty_boxes",
                semantic_hint=semantic,
                method="yolo_pose",
                source_path=str(image_path),
                output_path=str(image_path),
                body_visibility="unknown",
                confidence=0.0,
                crop_box=None,
            )
            if self.cfg.cache_crops:
                self._write_meta(cache_meta, asdict(decision))
            return image_path, decision

        conf_arr = (
            r0.boxes.conf.cpu().numpy()
            if getattr(r0.boxes, "conf", None) is not None
            else np.ones((boxes_xyxy.shape[0],), dtype=np.float32)
        )
        areas = (boxes_xyxy[:, 2] - boxes_xyxy[:, 0]) * (boxes_xyxy[:, 3] - boxes_xyxy[:, 1])
        scores = areas * conf_arr
        best_i = int(np.argmax(scores))

        bx1, by1, bx2, by2 = [float(v) for v in boxes_xyxy[best_i].tolist()]
        person_area_ratio = float(max(0.0, (bx2 - bx1)) * max(0.0, (by2 - by1)) / max(1.0, float(h * w)))
        if person_area_ratio < float(self.cfg.min_person_box_ratio):
            decision = AutoCropDecision(
                applied=False,
                reason="person_too_small",
                semantic_hint=semantic,
                method="yolo_pose",
                source_path=str(image_path),
                output_path=str(image_path),
                body_visibility="unknown",
                confidence=float(conf_arr[best_i]),
                crop_box=None,
            )
            if self.cfg.cache_crops:
                self._write_meta(cache_meta, asdict(decision))
            return image_path, decision

        kxy_all = r0.keypoints.xy.cpu().numpy()
        if best_i >= kxy_all.shape[0]:
            decision = AutoCropDecision(
                applied=False,
                reason="missing_keypoints_for_best_person",
                semantic_hint=semantic,
                method="yolo_pose",
                source_path=str(image_path),
                output_path=str(image_path),
                body_visibility="unknown",
                confidence=float(conf_arr[best_i]),
                crop_box=None,
            )
            if self.cfg.cache_crops:
                self._write_meta(cache_meta, asdict(decision))
            return image_path, decision

        kxy = kxy_all[best_i]
        kconf_all = getattr(r0.keypoints, "conf", None)
        kconf = kconf_all.cpu().numpy()[best_i] if kconf_all is not None else None

        shoulders = [p for p in [self._kp(kxy, kconf, 5), self._kp(kxy, kconf, 6)] if p is not None]
        hips = [p for p in [self._kp(kxy, kconf, 11), self._kp(kxy, kconf, 12)] if p is not None]
        knees = [p for p in [self._kp(kxy, kconf, 13), self._kp(kxy, kconf, 14)] if p is not None]
        ankles = [p for p in [self._kp(kxy, kconf, 15), self._kp(kxy, kconf, 16)] if p is not None]
        visibility = self._visibility(shoulders, hips, knees, ankles)

        pad = int(round(float(self.cfg.pad_ratio) * max(h, w)))
        ph = max(1.0, by2 - by1)

        cx1, cx2 = bx1, bx2
        if semantic == "tops":
            if not shoulders and not hips:
                decision = AutoCropDecision(
                    applied=False,
                    reason="no_upper_body_keypoints",
                    semantic_hint=semantic,
                    method="yolo_pose",
                    source_path=str(image_path),
                    output_path=str(image_path),
                    body_visibility=visibility,
                    confidence=float(conf_arr[best_i]),
                    crop_box=None,
                )
                if self.cfg.cache_crops:
                    self._write_meta(cache_meta, asdict(decision))
                return image_path, decision

            if hips:
                hip_y = float(np.mean([p[1] for p in hips]))
                if knees:
                    knee_y = float(np.mean([p[1] for p in knees]))
                    cy2 = hip_y + 0.22 * (knee_y - hip_y)
                else:
                    cy2 = hip_y + 0.10 * ph
            else:
                shoulder_y = float(np.mean([p[1] for p in shoulders])) if shoulders else by1
                cy2 = shoulder_y + 0.45 * ph
            cy1 = by1
        else:
            if not hips and not knees and not ankles:
                decision = AutoCropDecision(
                    applied=False,
                    reason="no_lower_body_keypoints",
                    semantic_hint=semantic,
                    method="yolo_pose",
                    source_path=str(image_path),
                    output_path=str(image_path),
                    body_visibility=visibility,
                    confidence=float(conf_arr[best_i]),
                    crop_box=None,
                )
                if self.cfg.cache_crops:
                    self._write_meta(cache_meta, asdict(decision))
                return image_path, decision

            if hips:
                hip_y = float(np.mean([p[1] for p in hips]))
                cy1 = hip_y - 0.05 * ph
            elif knees:
                knee_y = float(np.mean([p[1] for p in knees]))
                cy1 = knee_y - 0.35 * ph
            else:
                cy1 = by1 + 0.45 * ph
            cy2 = by2
            if ankles:
                ankle_y = float(np.mean([p[1] for p in ankles]))
                if knees:
                    knee_y = float(np.mean([p[1] for p in knees]))
                    shoe_line = ankle_y - float(self.cfg.shoe_cut) * (ankle_y - knee_y)
                else:
                    shoe_line = ankle_y - float(self.cfg.shoe_cut) * (0.12 * ph)
                cy2 = min(cy2, shoe_line + pad)

        x1, y1, x2, y2 = self._clip_box(
            cx1 - pad,
            cy1 - pad,
            cx2 + pad,
            cy2 + pad,
            w=w,
            h=h,
        )
        x1, y1, x2, y2 = self._tighten_full_body_box(
            x1,
            y1,
            x2,
            y2,
            semantic=semantic,
            visibility=visibility,
            person_area_ratio=person_area_ratio,
            shoulders=shoulders,
            hips=hips,
            knees=knees,
            ankles=ankles,
            w=w,
            h=h,
        )

        crop_area_ratio = float(max(0, x2 - x1) * max(0, y2 - y1) / max(1.0, float(h * w)))
        if crop_area_ratio < float(self.cfg.min_crop_area_ratio):
            decision = AutoCropDecision(
                applied=False,
                reason="crop_too_small",
                semantic_hint=semantic,
                method="yolo_pose",
                source_path=str(image_path),
                output_path=str(image_path),
                body_visibility=visibility,
                confidence=float(conf_arr[best_i]),
                crop_box=(x1, y1, x2, y2),
            )
            if self.cfg.cache_crops:
                self._write_meta(cache_meta, asdict(decision))
            return image_path, decision

        crop = img_bgr[y1:y2, x1:x2].copy()
        ok = cv2.imwrite(str(cache_img), crop)
        if not ok:
            decision = AutoCropDecision(
                applied=False,
                reason="failed_to_write_crop",
                semantic_hint=semantic,
                method="yolo_pose",
                source_path=str(image_path),
                output_path=str(image_path),
                body_visibility=visibility,
                confidence=float(conf_arr[best_i]),
                crop_box=(x1, y1, x2, y2),
            )
            if self.cfg.cache_crops:
                self._write_meta(cache_meta, asdict(decision))
            return image_path, decision

        decision = AutoCropDecision(
            applied=True,
            reason="ok",
            semantic_hint=semantic,
            method="yolo_pose",
            source_path=str(image_path),
            output_path=str(cache_img),
            body_visibility=visibility,
            confidence=float(conf_arr[best_i]),
            crop_box=(x1, y1, x2, y2),
        )
        if self.cfg.cache_crops:
            self._write_meta(cache_meta, asdict(decision))
        return cache_img, decision
