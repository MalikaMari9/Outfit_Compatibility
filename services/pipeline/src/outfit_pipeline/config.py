from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


@dataclass
class PathConfig:
    data_root: Path
    weights: Path
    output_dir: Path
    cache_dir: Path


@dataclass
class ScoreWeights:
    model: float = 0.70
    type_prior: float = 0.15
    color: float = 0.10
    brightness: float = 0.05
    pattern: float = 0.0

    def normalized(self) -> "ScoreWeights":
        total = self.model + self.type_prior + self.color + self.brightness + self.pattern
        if total <= 0:
            return ScoreWeights()
        return ScoreWeights(
            model=self.model / total,
            type_prior=self.type_prior / total,
            color=self.color / total,
            brightness=self.brightness / total,
            pattern=self.pattern / total,
        )


@dataclass
class RetrievalConfig:
    top_k: int = 5
    shortlist_k: int = 150
    candidate_splits: tuple[str, ...] = ("train", "valid")
    allow_test_candidates: bool = False
    batch_size: int = 64
    embedding_cache: bool = True


@dataclass
class ModelConfig:
    backbone: str = "resnet18"
    embed_dim: int = 256
    img_size: int = 224
    threshold: float = 0.62
    borderline_threshold: float = 0.55
    weak_threshold: float = 0.45
    excellent_threshold: float = 0.72


@dataclass
class PatternModelConfig:
    enabled: bool = True
    weights: Path = Path("assets/models/A_best_pattern_clean_colab.pt")
    threshold: float = 0.35
    min_reliability: float = 0.42
    fine_detail_guard: float = 0.58


@dataclass
class CategoryModelConfig:
    enabled: bool = True
    weights: Path = Path("assets/models/B_best_category_tempered.pt")
    mapping: Path = Path("assets/models/B_class_mapping_tempered.csv")
    topk: int = 3
    min_confidence: float = 0.08


@dataclass
class AutoCropConfig:
    enabled: bool = True
    weights: Path = Path("assets/models/yolov8n-pose.pt")
    conf: float = 0.25
    keypoint_conf: float = 0.20
    pad_ratio: float = 0.06
    shoe_cut: float = 0.35
    min_person_box_ratio: float = 0.03
    min_crop_area_ratio: float = 0.05
    full_body_tighten_ratio: float = 0.12
    cache_crops: bool = True


@dataclass
class ForegroundConfig:
    enabled: bool = True
    method: str = "segformer"
    cache_masks: bool = True
    alpha_threshold: int = 10
    min_mask_ratio: float = 0.01
    ignore_low_sat_bg: bool = True
    low_sat_threshold: int = 22
    near_white_v: int = 235
    near_black_v: int = 20
    segformer_model_id: str = "mattmdjaga/segformer_b2_clothes"
    segformer_target_labels: tuple[str, ...] = (
        "upper",
        "shirt",
        "blouse",
        "sweater",
        "jacket",
        "coat",
        "dress",
        "skirt",
        "pants",
        "trousers",
        "shorts",
        "jeans",
        "clothes",
        "apparel",
    )
    segformer_device: str = "auto"


@dataclass
class OllamaConfig:
    enabled: bool = False
    model: str = "qwen2.5:1.5b"
    host: str = "http://127.0.0.1:11434"
    timeout_sec: int = 60
    temperature: float = 0.1
    max_tokens: int = 160
    retries: int = 0
    cache_explanations: bool = True


@dataclass
class PipelineConfig:
    paths: PathConfig
    weights: ScoreWeights
    retrieval: RetrievalConfig
    model: ModelConfig
    pattern_model: PatternModelConfig
    category_model: CategoryModelConfig
    autocrop: AutoCropConfig
    foreground: ForegroundConfig
    ollama: OllamaConfig

    @classmethod
    def from_json(cls, path: str | Path) -> "PipelineConfig":
        p = Path(path).resolve()
        data = json.loads(p.read_text(encoding="utf-8"))
        project_root = p.parents[1] if len(p.parents) >= 2 else p.parent
        workspace_root = project_root.parent

        def _resolve_cfg_path(raw: str | Path, default_base: Path) -> Path:
            rp = Path(raw)
            if rp.is_absolute():
                return rp
            anchors = (project_root, workspace_root, p.parent, Path.cwd())
            for base in anchors:
                cand = (base / rp).resolve()
                if cand.exists():
                    return cand
            return (default_base / rp).resolve()

        paths = data.get("paths", {})
        weights = data.get("weights", {})
        retrieval = data.get("retrieval", {})
        model = data.get("model", {})
        pattern_model = data.get("pattern_model", {})
        category_model = data.get("category_model", {})
        autocrop = data.get("autocrop", {})
        foreground = data.get("foreground", {})
        ollama = data.get("ollama", {})
        split_values = [
            str(x).strip().lower()
            for x in retrieval.get("candidate_splits", ["train", "valid"])
            if str(x).strip()
        ]

        cfg = cls(
            paths=PathConfig(
                data_root=_resolve_cfg_path(
                    paths.get("data_root", "../../assets/data/polyvore_outfits"),
                    default_base=project_root,
                ),
                weights=_resolve_cfg_path(
                    paths.get("weights", "../../assets/models/compat_top_bottom.pt"),
                    default_base=project_root,
                ),
                output_dir=_resolve_cfg_path(
                    paths.get("output_dir", "../../runtime/pipeline_outputs"),
                    default_base=project_root,
                ),
                cache_dir=_resolve_cfg_path(
                    paths.get("cache_dir", "../../runtime/cache/pipeline"),
                    default_base=project_root,
                ),
            ),
            weights=ScoreWeights(
                model=float(weights.get("model", 0.70)),
                type_prior=float(weights.get("type_prior", 0.15)),
                color=float(weights.get("color", 0.10)),
                brightness=float(weights.get("brightness", 0.05)),
                pattern=float(weights.get("pattern", 0.0)),
            ).normalized(),
            retrieval=RetrievalConfig(
                top_k=int(retrieval.get("top_k", 5)),
                shortlist_k=int(retrieval.get("shortlist_k", 150)),
                candidate_splits=tuple(split_values) if split_values else ("train", "valid"),
                allow_test_candidates=bool(retrieval.get("allow_test_candidates", False)),
                batch_size=int(retrieval.get("batch_size", 64)),
                embedding_cache=bool(retrieval.get("embedding_cache", True)),
            ),
            model=ModelConfig(
                backbone=str(model.get("backbone", "resnet18")),
                embed_dim=int(model.get("embed_dim", 256)),
                img_size=int(model.get("img_size", 224)),
                threshold=float(model.get("threshold", 0.62)),
                borderline_threshold=float(model.get("borderline_threshold", 0.55)),
                weak_threshold=float(model.get("weak_threshold", 0.45)),
                excellent_threshold=float(model.get("excellent_threshold", 0.72)),
            ),
            pattern_model=PatternModelConfig(
                enabled=bool(pattern_model.get("enabled", True)),
                weights=_resolve_cfg_path(
                    pattern_model.get(
                        "weights",
                        "../../assets/models/A_best_pattern_clean_colab.pt",
                    ),
                    default_base=project_root,
                ),
                threshold=float(pattern_model.get("threshold", 0.35)),
                min_reliability=float(pattern_model.get("min_reliability", 0.42)),
                fine_detail_guard=float(pattern_model.get("fine_detail_guard", 0.58)),
            ),
            category_model=CategoryModelConfig(
                enabled=bool(category_model.get("enabled", True)),
                weights=_resolve_cfg_path(
                    category_model.get(
                        "weights",
                        "../../assets/models/B_best_category_tempered.pt",
                    ),
                    default_base=project_root,
                ),
                mapping=_resolve_cfg_path(
                    category_model.get(
                        "mapping",
                        "../../assets/models/B_class_mapping_tempered.csv",
                    ),
                    default_base=project_root,
                ),
                topk=max(1, int(category_model.get("topk", 3))),
                min_confidence=float(category_model.get("min_confidence", 0.08)),
            ),
            autocrop=AutoCropConfig(
                enabled=bool(autocrop.get("enabled", True)),
                weights=_resolve_cfg_path(
                    autocrop.get("weights", "../../assets/models/yolov8n-pose.pt"),
                    default_base=project_root,
                ),
                conf=float(autocrop.get("conf", 0.25)),
                keypoint_conf=float(autocrop.get("keypoint_conf", 0.20)),
                pad_ratio=float(autocrop.get("pad_ratio", 0.06)),
                shoe_cut=float(autocrop.get("shoe_cut", 0.35)),
                min_person_box_ratio=float(autocrop.get("min_person_box_ratio", 0.03)),
                min_crop_area_ratio=float(autocrop.get("min_crop_area_ratio", 0.05)),
                full_body_tighten_ratio=float(autocrop.get("full_body_tighten_ratio", 0.12)),
                cache_crops=bool(autocrop.get("cache_crops", True)),
            ),
            foreground=ForegroundConfig(
                enabled=bool(foreground.get("enabled", True)),
                method=str(foreground.get("method", "u2net")),
                cache_masks=bool(foreground.get("cache_masks", True)),
                alpha_threshold=int(foreground.get("alpha_threshold", 10)),
                min_mask_ratio=float(foreground.get("min_mask_ratio", 0.01)),
                ignore_low_sat_bg=bool(foreground.get("ignore_low_sat_bg", True)),
                low_sat_threshold=int(foreground.get("low_sat_threshold", 22)),
                near_white_v=int(foreground.get("near_white_v", 235)),
                near_black_v=int(foreground.get("near_black_v", 20)),
                segformer_model_id=str(
                    foreground.get("segformer_model_id", "mattmdjaga/segformer_b2_clothes")
                ),
                segformer_target_labels=tuple(
                    foreground.get(
                        "segformer_target_labels",
                        [
                            "upper",
                            "shirt",
                            "blouse",
                            "sweater",
                            "jacket",
                            "coat",
                            "dress",
                            "skirt",
                            "pants",
                            "trousers",
                            "shorts",
                            "jeans",
                            "clothes",
                            "apparel",
                        ],
                    )
                ),
                segformer_device=str(foreground.get("segformer_device", "auto")),
            ),
            ollama=OllamaConfig(
                enabled=bool(ollama.get("enabled", False)),
                model=str(ollama.get("model", "qwen2.5:1.5b")),
                host=str(ollama.get("host", "http://127.0.0.1:11434")),
                timeout_sec=max(1, int(ollama.get("timeout_sec", 60))),
                temperature=float(ollama.get("temperature", 0.1)),
                max_tokens=max(0, int(ollama.get("max_tokens", 160))),
                retries=max(0, int(ollama.get("retries", 0))),
                cache_explanations=bool(ollama.get("cache_explanations", True)),
            ),
        )

        cfg.paths.output_dir.mkdir(parents=True, exist_ok=True)
        cfg.paths.cache_dir.mkdir(parents=True, exist_ok=True)
        return cfg
