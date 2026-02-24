# Self-Contained Migration Log
Date: 2026-02-23

## Completed in This Pass
- Created self-contained structure under `OutfitCompatibility`:
  - `services/pipeline`
  - `services/llm`
  - `assets/models`
  - `assets/data`
  - `runtime/cache`
  - `runtime/uploads`
  - `docs`
- Copied pipeline code from old folder into `services/pipeline`:
  - `src`, `scripts`, `configs`, `requirements.txt`, `README.md`, `implementation_fix.md`
- Copied Ollama helper files into `services/llm`:
  - `chat_rag.py`, `index_kb.py`, `README.md`, `kb/`
- Copied required model files into `assets/models`:
  - `compat_top_bottom.pt`
  - `A_best_pattern_clean_colab.pt`
  - `B_best_category_tempered.pt`
  - `B_class_mapping_tempered.csv`
  - `yolov8n-pose.pt`
- Copied Polyvore data into `assets/data/polyvore_outfits`.
- Updated pipeline config paths to use only repo-local paths.
- Updated pipeline default fallback paths in `services/pipeline/src/outfit_pipeline/config.py` to repo-local paths.
- Extended `.gitignore` for runtime/cache artifacts and local dev directories.

## Validation Performed
- `python services/pipeline/scripts/run_pair.py --help` passes.
- `python services/pipeline/scripts/run_rank.py --help` passes.
- End-to-end pair smoke test passes from copied `assets/data` with default config.
- Config path existence check passes for all required model/data paths.

## Pending Next Step
- Integrate backend routes (`/compatibility`, `/recommend`, `/feedback`) with the moved pipeline under `services/pipeline` so frontend uses this self-contained stack.
