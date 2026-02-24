from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import torch
from PIL import Image
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms


def default_transform(img_size: int = 224) -> transforms.Compose:
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


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_metadata(data_root: Path) -> Dict[str, dict]:
    return load_json(data_root / "polyvore_item_metadata.json")


def build_set_index(split_json: Path) -> Dict[str, Dict[int, str]]:
    outfits = load_json(split_json)
    index: Dict[str, Dict[int, str]] = {}
    for outfit in outfits:
        set_id = str(outfit["set_id"])
        items = {int(it["index"]): str(it["item_id"]) for it in outfit["items"]}
        index[set_id] = items
    return index


def load_compatibility_lines(path: Path) -> List[Tuple[int, List[str]]]:
    lines: List[Tuple[int, List[str]]] = []
    with path.open("r", encoding="utf-8") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            parts = raw.split()
            lines.append((int(parts[0]), parts[1:]))
    return lines


def resolve_token(token: str, set_index: Dict[str, Dict[int, str]]) -> Optional[str]:
    try:
        set_id, idx = token.split("_")
        return set_index.get(set_id, {}).get(int(idx))
    except ValueError:
        return None


def semantic_category(item_id: str, metadata: Dict[str, dict]) -> str:
    return (metadata.get(item_id, {}).get("semantic_category") or "").strip()


def category_id(item_id: str, metadata: Dict[str, dict]) -> str:
    return str(metadata.get(item_id, {}).get("category_id") or "").strip()


def items_by_semantic(
    tokens: List[str],
    set_index: Dict[str, Dict[int, str]],
    metadata: Dict[str, dict],
    target: str,
) -> List[str]:
    out: List[str] = []
    seen = set()
    for token in tokens:
        item_id = resolve_token(token, set_index)
        if not item_id:
            continue
        if semantic_category(item_id, metadata) != target:
            continue
        if item_id in seen:
            continue
        seen.add(item_id)
        out.append(item_id)
    return out


def list_items_by_semantic(data_root: Path, target: str, splits: Iterable[str]) -> List[str]:
    metadata = load_metadata(data_root)
    images_dir = data_root / "images"

    out = set()
    for split in splits:
        split_json = data_root / "disjoint" / f"{split}.json"
        outfits = load_json(split_json)
        for outfit in outfits:
            for it in outfit["items"]:
                item_id = str(it["item_id"])
                if semantic_category(item_id, metadata) != target:
                    continue
                if not (images_dir / f"{item_id}.jpg").exists():
                    continue
                out.add(item_id)
    return sorted(out)


def build_type_prior_map(
    data_root: Path,
    cache_path: Optional[Path] = None,
    alpha: float = 1.0,
) -> Dict[str, float]:
    split_dir = data_root / "disjoint"
    train_json = split_dir / "train.json"
    compat_train = split_dir / "compatibility_train.txt"
    metadata_json = data_root / "polyvore_item_metadata.json"

    fp = hashlib.sha1()
    fp.update(f"alpha={float(alpha):.6f}".encode("utf-8"))
    for src in (train_json, compat_train, metadata_json):
        st = src.stat()
        fp.update(str(src.resolve()).encode("utf-8"))
        fp.update(str(st.st_size).encode("utf-8"))
        fp.update(str(st.st_mtime_ns).encode("utf-8"))
    fingerprint = fp.hexdigest()

    if cache_path is not None and cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if isinstance(cached, dict) and "_meta" in cached and "table" in cached:
                meta = cached.get("_meta", {})
                table = cached.get("table", {})
                if str(meta.get("fingerprint", "")) == fingerprint and isinstance(table, dict):
                    return {str(k): float(v) for k, v in table.items()}
        except Exception:
            # Ignore unreadable/legacy cache and rebuild.
            pass

    metadata = load_metadata(data_root)
    set_index = build_set_index(train_json)
    lines = load_compatibility_lines(compat_train)

    pos: Dict[Tuple[str, str], int] = {}
    neg: Dict[Tuple[str, str], int] = {}

    for label, tokens in lines:
        tops = items_by_semantic(tokens, set_index, metadata, "tops")
        bottoms = items_by_semantic(tokens, set_index, metadata, "bottoms")
        if not tops or not bottoms:
            continue

        for top_id in tops:
            for bottom_id in bottoms:
                tc = category_id(top_id, metadata)
                bc = category_id(bottom_id, metadata)
                if not tc or not bc:
                    continue
                key = (tc, bc)
                if label == 1:
                    pos[key] = pos.get(key, 0) + 1
                else:
                    neg[key] = neg.get(key, 0) + 1

    out: Dict[str, float] = {}
    keys = set(pos.keys()) | set(neg.keys())
    for tc, bc in keys:
        p = float(pos.get((tc, bc), 0))
        n = float(neg.get((tc, bc), 0))
        score = (p + alpha) / (p + n + 2.0 * alpha)
        out[f"{tc}|{bc}"] = float(score)

    if cache_path is not None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_payload = {
            "_meta": {
                "fingerprint": fingerprint,
                "alpha": float(alpha),
            },
            "table": out,
        }
        cache_path.write_text(json.dumps(cache_payload), encoding="utf-8")

    return out


def infer_item_id_from_path(path: Path, metadata: Dict[str, dict]) -> Optional[str]:
    stem = path.stem.strip()
    if stem in metadata:
        return stem
    return None


def item_text(item_id: str, metadata: Dict[str, dict]) -> str:
    row = metadata.get(item_id, {})
    chunks = [
        str(row.get("title") or ""),
        str(row.get("description") or ""),
        str(row.get("url_name") or ""),
    ]
    rel = row.get("related")
    if isinstance(rel, list):
        chunks.extend(str(x) for x in rel)
    elif rel:
        chunks.append(str(rel))
    return " ".join(chunks).lower()


def get_item_category(item_id: str, metadata: Dict[str, dict]) -> str:
    return category_id(item_id, metadata)


def load_category_lookup(data_root: Path) -> Dict[str, dict]:
    categories_csv = data_root / "categories.csv"
    if not categories_csv.exists():
        return {}

    out: Dict[str, dict] = {}
    with categories_csv.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cid = str(row.get("category_id") or "").strip()
            if not cid:
                continue
            sub = str(row.get("sub_category") or "").strip()
            main = str(row.get("main_category") or "").strip()

            slot = out.setdefault(
                cid,
                {
                    "main_category": main,
                    "sub_category": sub,
                    "aliases": [],
                },
            )
            if not slot["main_category"] and main:
                slot["main_category"] = main
            if not slot["sub_category"] and sub:
                slot["sub_category"] = sub
            if sub and sub not in slot["aliases"]:
                slot["aliases"].append(sub)

    return out


def load_bgr(path: Path):
    import cv2

    img = cv2.imread(str(path))
    if img is None:
        raise FileNotFoundError(f"Failed to read image: {path}")
    return img


class ItemImageDataset(Dataset):
    def __init__(self, item_ids: List[str], images_dir: Path, tf: transforms.Compose):
        self.item_ids = item_ids
        self.images_dir = images_dir
        self.tf = tf

    def __len__(self):
        return len(self.item_ids)

    def __getitem__(self, idx):
        item_id = self.item_ids[idx]
        img_path = self.images_dir / f"{item_id}.jpg"
        img = Image.open(img_path).convert("RGB")
        return self.tf(img), item_id


@torch.no_grad()
def build_embeddings(
    model,
    item_ids: List[str],
    images_dir: Path,
    img_size: int,
    batch_size: int,
    device: torch.device,
) -> Tuple[np.ndarray, List[str]]:
    tf = default_transform(img_size)
    ds = ItemImageDataset(item_ids, images_dir, tf)
    loader = DataLoader(ds, batch_size=batch_size, shuffle=False, num_workers=0)

    all_embs = []
    all_ids: List[str] = []
    model.eval()

    for batch, batch_ids in loader:
        batch = batch.to(device, non_blocking=True)
        emb = model.encode(batch).detach().cpu().numpy()
        all_embs.append(emb)
        all_ids.extend(batch_ids)

    if not all_embs:
        return np.zeros((0, 1), dtype=np.float32), []
    return np.vstack(all_embs).astype(np.float32), all_ids


def save_embedding_cache(path: Path, embs: np.ndarray, ids: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, embs=embs, ids=np.array(ids, dtype=object))


def load_embedding_cache(path: Path) -> Tuple[np.ndarray, List[str]]:
    data = np.load(path, allow_pickle=True)
    return data["embs"].astype(np.float32), data["ids"].tolist()
