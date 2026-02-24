# Implementation Fix Log

## 2026-02-23 - Polyvore Decoupling Plan (Discussion Notes)

Goal: remove Polyvore as a runtime special-case while keeping compatibility quality stable.

### Replacements Required
1. Catalog source of truth
- Add a unified catalog store (json/csv/db) with: `item_id`, `image_path`, `semantic` (`tops`/`bottoms`), `category_id`, `category_name`, `active`.
- This replaces Polyvore split-based listing and path assumptions.

2. Unified metadata resolver
- Resolve metadata/category from catalog first, not from Polyvore-path checks.
- For unknown uploads, keep classifier-based fallback for category/pattern/visual features.

3. Candidate pool/index replacement
- Build retrieval candidates from active catalog entries.
- Keep embedding cache, but add a catalog fingerprint/version in cache key so candidate changes invalidate cache.

4. Type-prior replacement
- Current type prior comes from Polyvore compatibility labels.
- Replace with:
  - preferred: priors from our own labeled top-bottom pairs
  - temporary: neutral prior (`0.5`) with lower type-prior weight until labels are collected.

5. Internal category taxonomy
- Define stable internal categories (shirt/tee/jeans/skirt/etc.) and maintain mapping from model outputs.
- Prevent category-id drift from external datasets.

6. Own supervision data
- Collect internal positive/negative top-bottom compatibility pairs.
- Needed for retraining or calibration of model score and fusion fairness.

7. Calibration/evaluation set
- Keep a held-out internal benchmark to tune fusion weights and 5-band thresholds.
- Re-tune whenever model/data/taxonomy changes.

### Keep These Fixes Regardless of Polyvore Removal
- Fix 1: cache corruption fallback/rebuild (still required).
- Fix 2: stale embedding cache invalidation using data/catalog fingerprint (still required).

### Recommendation
- Remove Polyvore as runtime branching first.
- Keep Polyvore only as temporary offline source until internal data is sufficient.
- Then phase out Polyvore dependencies fully.

## 2026-02-23 - Ollama Explanation Layer Spec (No-Scoring)

Goal: integrate Ollama for human-readable explanation only.

### Decision
- Ollama is an explanation layer.
- Numeric compatibility score and label remain fully owned by deterministic pipeline.
- Ollama must not modify `final_score`, `breakdown`, or label band.

### Scope (Phase 1)
1. Pair mode only.
2. Retrieval mode top-1 only (expand later to top-3 if stable).

### Required Config (proposed)
- `ollama.enabled` (bool, default `false`)
- `ollama.model` (string, e.g. `mistral:latest`)
- `ollama.host` (string, default `http://127.0.0.1:11434`)
- `ollama.timeout_sec` (int, default `60`)
- `ollama.temperature` (float, default `0.2`)
- `ollama.max_tokens` (int, default `0`, where `0` means Ollama/model default length)
- `ollama.retries` (int, default `1`)
- `ollama.cache_explanations` (bool, default `true`)

### Input Contract to Ollama
Send structured facts only (no raw image assumptions):
- Pair identifiers: `top_image`, `bottom_image`
- Output decision: `label`, `final_score`
- Score breakdown: `model`, `type_prior`, `color`, `brightness`, `pattern`
- Thresholds: `weak`, `borderline`, `good`, `excellent`
- Metadata facts:
  - `top_category_name`, `bottom_category_name`
  - `top_primary_color`, `bottom_primary_color`
  - `top_category_source`, `bottom_category_source`
  - `top_mask_fallback`, `bottom_mask_fallback`
  - `top_autocrop.reason`, `bottom_autocrop.reason` (if present)

### Output Contract from Ollama (strict JSON)
Ollama must return valid JSON object with exactly these keys:
- `summary` (string, 1-2 sentences)
- `why_it_works` (array of 2-4 short bullet strings)
- `risk_points` (array of 0-3 short bullet strings)
- `style_suggestion` (string, 1 sentence)
- `confidence_note` (string: `high` | `medium` | `low`)
- `disclaimer` (string: must state explanation does not alter score)

If parse fails:
- set `llm_status = "invalid_json"`
- store raw text under `llm_raw`
- do not block pipeline result

### Prompt Contract (template)
System instruction (fixed):
- Explain outfit compatibility from provided numeric/component facts only.
- Never invent unseen item details.
- Never propose a different score/label.
- Return strict JSON with required keys only.

User payload (structured):
- Include all fields from "Input Contract to Ollama".
- Include rule reminder: "If components conflict, explain tradeoff (e.g., strong color harmony but weaker model confidence)."

### Runtime/Fallback Rules
1. If Ollama disabled: `llm_status = "disabled"`.
2. If server unreachable/timeout: `llm_status = "unavailable"` and continue.
3. If response non-JSON: `llm_status = "invalid_json"` and continue.
4. If success: `llm_status = "ok"` and attach `llm_explanation` object.

### Caching Strategy
- Cache key hash should include:
  - score breakdown values
  - final score + label
  - relevant metadata facts used in prompt
  - prompt version
  - model name
- Rationale: repeated queries with same facts should not regenerate text.

### UI/CLI Integration
- Pair JSON output: add `llm_status`, optional `llm_explanation`, optional `llm_raw`.
- Retrieval JSON output: same fields per ranked row in phase 2.
- GUI: show explanation text in result panel when available.

### Acceptance Criteria
1. Pipeline result remains available even when Ollama fails.
2. No Ollama response can mutate score or label.
3. >=95% of successful calls return valid JSON object matching schema.
4. Average explanation latency under configured timeout.
5. Explanations reflect actual breakdown tradeoffs (no contradictions).

### Rollout Order
1. Implement adapter + config + pair mode only.
2. Add schema validation + fallback states.
3. Add explanation cache.
4. Expand to retrieval top-1.
5. Evaluate quality on 20-30 examples across all 5 label bands.

### 2026-02-23 Implementation Status
- Completed phase-1 integration:
  - `ollama` config block added in `configs/pipeline_config.json`.
  - adapter module added: `src/outfit_pipeline/ollama_explainer.py`.
  - pair pipeline now attaches:
    - `llm_status` (`disabled|unavailable|invalid_json|ok`)
    - optional `llm_explanation`
    - optional `llm_raw`, `llm_error`
    - `llm_cached` flag.
- Guardrails enforced:
  - no mutation of final numeric score or label.
  - fallback behavior keeps pipeline output available when Ollama fails.
- Not yet implemented:
  - none for planned phase-2 scope.

### 2026-02-23 Phase-2 Update (Applied)
- Retrieval integration added for top-1 candidate explanation:
  - rank-1 row now receives `llm_status`, `llm_cached`, and optional `llm_explanation`.
  - fallback fields `llm_raw` / `llm_error` are attached when needed.
- Scope control:
  - only rank-1 receives LLM fields (as specified).
  - rank-2+ rows are unchanged.
- Validation checks run:
  - default config (`ollama.enabled=false`) -> rank-1 shows `llm_status=disabled`.
  - forced unavailable host -> rank-1 shows `llm_status=unavailable` with error.

### 2026-02-23 Integration Guardrails (Applied)
- Output sanitization for integration:
  - Added `to_public_dict()` on pair and retrieval outputs to redact local filesystem paths.
  - Added CLI flags:
    - `scripts/run_pair.py --public-output`
    - `scripts/run_rank.py --public-output`
- Explanation contract hardening:
  - `disclaimer` is now forced to: `Explanation only; score and label are unchanged.`
  - prevents model-specific disclaimer drift.
- Backend upload hardening (in `OutfitCompatibility/backend`):
  - image MIME filter (`jpeg/png/webp/bmp`)
  - upload size limit via `MAX_UPLOAD_MB` (default 10MB)
  - multer error handling in app middleware
  - health endpoints:
    - `GET /health`
    - `GET /health/ollama`

