# Outfit Compatibility Pipeline (2026-02-22)

Reusable, context-free outfit compatibility pipeline built for:
- `top -> bottom` top-5 retrieval
- `bottom -> top` top-5 retrieval
- pair compatibility calculator (`top + bottom`)

This project is self-contained under `OutfitCompatibility` and uses repo-local data/models by default.

## Default Data/Model Paths
- Data root: `../../assets/data/polyvore_outfits` (resolved from `configs/pipeline_config.json`)
- Model weights: `../../assets/models/compat_top_bottom.pt`

## Structure
- `configs/pipeline_config.json`: runtime paths and scoring weights
- `src/outfit_pipeline/`: reusable pipeline package
- `scripts/run_pair.py`: pair compatibility calculator
- `scripts/run_rank.py`: top-k retrieval (`top2bottom` / `bottom2top`)
- `scripts/run_gui.py`: Tkinter debug GUI
- `notebooks/2026-02-22_pipeline_summary.ipynb`: implementation summary notebook

## Install
```bash
pip install -r requirements.txt
```

## Quick Start
```bash
python scripts/run_pair.py --top-image path/to/top.jpg --bottom-image path/to/bottom.jpg
python scripts/run_pair.py --top-image path/to/top.jpg --bottom-image path/to/bottom.jpg --bg-method u2net
python scripts/run_pair.py --top-image path/to/top.jpg --bottom-image path/to/bottom.jpg --public-output
python scripts/run_rank.py --mode top2bottom --query-image path/to/top.jpg --top-k 5
python scripts/run_rank.py --mode top2bottom --query-image path/to/top.jpg --top-k 5 --bg-method segformer
python scripts/run_rank.py --mode top2bottom --query-image path/to/top.jpg --top-k 5 --public-output
python scripts/run_gui.py
```

## Notes
- Retrieval runs 2-stage ranking:
  1. cosine shortlist on embeddings
  2. fused rerank (`model + type_prior + color + brightness + pattern`)
- Type prior is learned from Polyvore disjoint train compatibility lines and cached with source-file fingerprinting (auto-invalidates on data changes).
- Pattern signal now uses the image model from:
  `../../assets/models/A_best_pattern_clean_colab.pt`
  with automatic fallback to text heuristic if unavailable.
- Category/type now falls back to the image model from:
  `../../assets/models/B_best_category_tempered.pt`
  when input images are outside the dataset folder.
- If fallback confidence is too low, category is left blank and `category_source=image_model_low_confidence`.
- Retrieval defaults to `train+valid` candidates only; `test` candidates are blocked unless `allow_test_candidates=true`.
- Embedding caches include a model-weights fingerprint so stale candidate embeddings are not reused after model updates.
- Labels now support a 5-band scale: `Excellent Match`, `Good Match`, `Borderline Acceptable`, `Weak Match`, `Mismatch`.
- For non-metadata/OOD category cases, fusion applies adaptive weighting to reduce model over-dominance.
- External uploads now auto-detect full-body vs product images using YOLO pose and auto-crop by semantic hint (`tops`/`bottoms`) with safe fallback.
- Background-removal modes are selectable: `none`, `rembg`, `u2net`, `u2netp`, `isnet`, `segformer`.
- Foreground masks are cached in `outputs/cache/masks/` to keep repeated tests fast.
- Optional Ollama explanation layer is available in pair mode (config: `ollama.enabled`).
- Retrieval mode now also supports Ollama explanation for rank-1 candidate.
- Ollama never changes score/label; it only adds `llm_status` and optional `llm_explanation` in output details.
- If your local model is slow, raise `ollama.timeout_sec` in config.
- CLI supports `--public-output` to redact local filesystem paths for frontend/backend responses.
