from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

import torch
import torch.nn as nn
from PIL import Image
from torchvision import models, transforms


TOP_CATEGORY_NAMES = {
    "anorak",
    "blazer",
    "blouse",
    "bomber",
    "button-down",
    "cardigan",
    "flannel",
    "halter",
    "henley",
    "hoodie",
    "jacket",
    "jersey",
    "parka",
    "peacoat",
    "poncho",
    "sweater",
    "tank",
    "tee",
    "top",
    "turtleneck",
    "coat",
    "coverup",
    "kimono",
}


BOTTOM_CATEGORY_NAMES = {
    "capris",
    "chinos",
    "culottes",
    "cutoffs",
    "gauchos",
    "jeans",
    "jeggings",
    "jodhpurs",
    "joggers",
    "leggings",
    "sarong",
    "shorts",
    "skirt",
    "sweatpants",
    "sweatshorts",
    "trunks",
}


@dataclass(frozen=True)
class ClassInfo:
    class_index: int
    orig_manifest_category_id: int
    category_name: str


@dataclass(frozen=True)
class CategoryPrediction:
    class_index: int
    category_id: str
    category_name: str
    prob: float


def _build_category_model(num_classes: int) -> nn.Module:
    model = models.resnet18(weights=None)
    model.fc = nn.Linear(model.fc.in_features, num_classes)
    return model


def _category_transform(img_size: int) -> transforms.Compose:
    return transforms.Compose(
        [
            transforms.Resize((img_size, img_size)),
            transforms.ToTensor(),
            transforms.Normalize(
                mean=[0.485, 0.456, 0.406],
                std=[0.229, 0.224, 0.225],
            ),
        ]
    )


def _allowed_names_for_semantic(semantic_hint: str) -> set[str]:
    sem = semantic_hint.strip().lower()
    if sem == "tops":
        return TOP_CATEGORY_NAMES
    if sem == "bottoms":
        return BOTTOM_CATEGORY_NAMES
    return set()


def infer_semantic_from_category_name(category_name: str) -> str:
    name = category_name.strip().lower()
    if name in TOP_CATEGORY_NAMES:
        return "tops"
    if name in BOTTOM_CATEGORY_NAMES:
        return "bottoms"
    return ""


def load_class_mapping(csv_path: Path) -> Dict[int, ClassInfo]:
    if not csv_path.exists():
        raise FileNotFoundError(f"Missing category mapping file: {csv_path}")

    out: Dict[int, ClassInfo] = {}
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            idx = int(row["class_index"])
            out[idx] = ClassInfo(
                class_index=idx,
                orig_manifest_category_id=int(row["orig_manifest_category_id"]),
                category_name=str(row["category_name"] or "").strip(),
            )

    if not out:
        raise RuntimeError(f"Empty category mapping: {csv_path}")
    return out


class CategoryPredictor:
    def __init__(self, weights_path: Path, mapping_path: Path, device: torch.device, img_size: int = 224):
        self.weights_path = Path(weights_path)
        self.mapping_path = Path(mapping_path)
        self.device = device

        if not self.weights_path.exists():
            raise FileNotFoundError(f"Category weights not found: {self.weights_path}")
        if not self.mapping_path.exists():
            raise FileNotFoundError(f"Category mapping not found: {self.mapping_path}")

        self.idx2info = load_class_mapping(self.mapping_path)
        self.model = _build_category_model(num_classes=len(self.idx2info))

        ckpt = torch.load(self.weights_path, map_location="cpu")
        state_dict = ckpt.get("model_state", ckpt) if isinstance(ckpt, dict) else ckpt
        self.model.load_state_dict(state_dict, strict=True)
        self.model.eval().to(self.device)
        self.tf = _category_transform(img_size=img_size)

    @torch.no_grad()
    def predict_topk(
        self,
        img: Image.Image,
        topk: int = 5,
        semantic_hint: str = "",
    ) -> List[CategoryPrediction]:
        x = self.tf(img.convert("RGB")).unsqueeze(0).to(self.device)
        probs = torch.softmax(self.model(x), dim=1)[0].detach().cpu().numpy()
        order = probs.argsort()[::-1].tolist()

        all_rows: List[CategoryPrediction] = []
        allowed_rows: List[CategoryPrediction] = []
        allowed_names = _allowed_names_for_semantic(semantic_hint)

        for idx in order:
            info = self.idx2info.get(int(idx))
            if info is None:
                continue
            pred = CategoryPrediction(
                class_index=info.class_index,
                category_id=str(info.orig_manifest_category_id),
                category_name=info.category_name,
                prob=float(probs[int(idx)]),
            )
            all_rows.append(pred)
            if allowed_names and pred.category_name.strip().lower() in allowed_names:
                allowed_rows.append(pred)

        rows = allowed_rows if allowed_rows else all_rows
        k = min(max(1, int(topk)), len(rows))
        return rows[:k]
