# OutfitCompatibility: Computer Vision Project Proposal Report

## Tech Stack
- Frontend: React, TypeScript, Vite, Tailwind CSS, shadcn/radix UI
- Backend: Node.js, Express, MongoDB (Mongoose), JWT, Multer
- CV/ML Pipeline: Python, PyTorch, torchvision, NumPy, OpenCV
- CV Models:
- `compat_top_bottom.pt` for pair compatibility scoring
- `B_best_category_tempered.pt` for category fallback on external images
- `A_best_pattern_clean_colab.pt` for pattern prediction
- `yolov8n-pose.pt` for auto body visibility and crop guidance
- Segmentation/Background Removal: rembg/U2Net/ISNet/SegFormer options
- LLM Explanation Layer: Ollama (Qwen 2.5) via deferred `/explain` API
- Datasets:
- Polyvore outfits (disjoint train/valid/test and compatibility metadata)
- DeepFashion Category and Attribute Prediction Benchmark (for category and pattern model training)

## Abstract
OutfitCompatibility is a computer vision system for evaluating outfit pair compatibility and recommending matching clothing items. The project combines deep visual embeddings, category priors, foreground-aware visual feature extraction, and pattern analysis to compute a final compatibility score. It supports two main use-cases: direct top-bottom compatibility checking and single-item recommendation (top to bottom or bottom to top). A hybrid retrieval strategy prioritizes user wardrobe items and uses Polyvore references as fallback. The architecture is designed as a full-stack deployable system with a React frontend, Express backend, and a Python inference pipeline. The project uses two datasets with different roles: Polyvore for compatibility/retrieval learning and DeepFashion for training the category and pattern classifiers integrated in inference. To improve user trust and explainability, the system exposes structured score breakdowns and optional natural-language explanations through an Ollama-based stylist layer. Current limitations such as LLM latency, out-of-distribution category confidence, and first-run cache warmup are identified and included as part of the proposed extension plan.

## Introduction
Modern wardrobe assistant systems require more than image classification. Practical adoption depends on four properties: visual understanding, compatibility reasoning, response speed, and user-facing explainability. This project addresses those needs with a context-free computer vision pipeline that can operate on user-uploaded photos and dataset references.

The system is built to bridge research-style compatibility scoring and production-style API behavior. It includes robust preprocessing (autocrop and foreground masking), score fusion with interpretable components, hybrid recommendation from personal wardrobe plus dataset fallback, and frontend modules that present confidence and explanation to non-technical users.

## Aim and Objectives
### Aim
Develop a reusable and explainable computer vision pipeline that evaluates outfit compatibility and recommends matching clothing pieces in a full-stack application setting.

### Objectives
1. Build a reliable pair-scoring model for top-bottom compatibility.
2. Support single-image recommendation with automatic direction detection.
3. Reduce background interference using segmentation and body-aware crop logic.
4. Integrate category, color, brightness, and pattern signals into a unified score.
5. Prioritize wardrobe-based recommendations before dataset fallback.
6. Provide user-readable explanation without modifying core scoring decisions.
7. Keep implementation self-contained under one repository for reproducible deployment.

## Theory
### Compatibility as Multi-Signal Fusion
Outfit compatibility is modeled as a weighted combination of learned and handcrafted signals:
- Learned pair compatibility from embedding-based neural scoring.
- Type prior from category co-occurrence statistics in training pairs.
- Color harmony from dominant palette relations.
- Brightness balance from masked visual metrics.
- Pattern compatibility from model predictions or fallback heuristics.

This design reflects the theory that style compatibility is not fully captured by a single representation. A robust solution requires both data-driven learning and constrained visual rules.

### Embedding-Based Pair Scoring
Each clothing image is encoded into a feature embedding. Pair interaction is modeled by concatenating direct and element-wise interactions between embeddings. A classifier head produces a base compatibility probability through a sigmoid output.

### Category Prior Probability
A Laplace-smoothed prior is computed from positive and negative top-bottom pair frequency:
`T(tc,bc) = (pos + alpha) / (pos + neg + 2*alpha)`
with `alpha = 1.0`.
This prior stabilizes scoring for semantically common pairings and acts as a probabilistic regularizer.

### Visual Feature Theory
Foreground-aware metrics are used to reduce background bias:
- Color harmony is computed from weighted dominant palette matching.
- Brightness compatibility uses Gaussian penalties on brightness/saturation/contrast differences.
- Pattern compatibility balances solid-pattern interactions and pattern similarity.

## Method
### 1. Data and Assets
- Polyvore disjoint split metadata and images for:
- pair compatibility learning signal
- type-prior computation
- retrieval candidate pool and fallback references
- DeepFashion Category and Attribute Prediction Benchmark for:
- category classifier training (`B2_trainCategory.py`)
- pattern classifier training (`A3_TrainPatternClean.py`)
- Local model checkpoints for pair compatibility, pattern prediction, and category fallback are exported from these training pipelines.
- User wardrobe images persisted in MongoDB and runtime upload storage.

### Dataset Usage Clarification
1. Polyvore (compatibility dataset):
- Used in deployment-time pipeline for compatibility logic and retrieval.
- Drives type prior table and candidate ranking pool.

2. DeepFashion (supervised classifier training dataset):
- Used offline to train category and pattern models.
- Trained weights and class mappings are then imported into the OutfitCompatibility runtime (`assets/models`).

### 2. Preprocessing Pipeline
1. Accept uploaded image(s) through backend API.
2. Auto-detect body visibility with YOLO pose and apply semantic crop hints.
3. Generate foreground mask with selected remover (U2Net/SegFormer/etc.).
4. Extract masked visual features (color, brightness metrics).
5. Infer category via metadata match or fallback category model for external images.
6. Infer pattern using pattern model or text heuristic fallback.

### 3. Scoring Strategy
Final score is computed as weighted fusion:
`final = w_m*M + w_t*T + w_c*C + w_b*B + w_p*P`

Current default weights:
- model: 0.60
- type_prior: 0.15
- color: 0.12
- brightness: 0.08
- pattern: 0.05

Five-band labels:
- Excellent Match
- Good Match
- Borderline Acceptable
- Weak Match
- Mismatch

### 4. Recommendation Strategy
- Auto mode infers whether upload is top or bottom.
- Retrieval shortlist uses embedding cosine similarity.
- Final rerank applies full compatibility fusion.
- Hybrid mode fills top results from wardrobe first, then Polyvore fallback.
- Candidate previews use crop-only policy for cleaner visual relevance.

### 5. Explainability Strategy
- Core score is deterministic and unchanged by LLM output.
- Explanation runs asynchronously via `/explain` to avoid blocking primary response.
- Fallback deterministic explanation is used when LLM output is invalid.

## System Implementation
### A. Frontend Layer
- `MixMatch.tsx`: uploads top and bottom, calls `/compatibility`, then `/explain`.
- `GlowUp.tsx`: uploads one item, calls `/recommend`, then `/explain`.
- `MyWardrobe.tsx`: CRUD wardrobe items and image uploads.
- Structured result cards show score bands, component bars, and explanation status.

### B. Backend Layer
- Express routes: `/compatibility`, `/recommend`, `/explain`, `/wardrobe`, `/feedback`.
- Multer upload handling with temporary and persistent paths.
- JWT-based user authentication and route-level user context.
- Python bridge executes pipeline scripts and sanitizes public response payloads.
- MongoDB required at startup by project policy.

### C. Pipeline Layer
- Main engine: `services/pipeline/src/outfit_pipeline/engine.py`.
- Pair scoring script: `run_pair.py`.
- Recommendation scripts: `run_recommend.py`, `run_recommend_hybrid.py`.
- Feature extractor for wardrobe cache/backfill: `run_extract_item_features.py`.
- Explanation script: `run_explain.py`.

### D. Caching and Runtime
- Embedding cache and type-prior cache reduce repeated heavy computation.
- Runtime directories are repo-local (`runtime/uploads`, `runtime/cache`).
- Cold-start latency is higher when caches are first built, then decreases.

### E. Known Limitations (Current)
1. LLM explanation latency remains a bottleneck for user-perceived responsiveness.
2. External/OOD category confidence can be low for difficult images.
3. First-run recommendation can take longer during embedding cache warmup.
4. Some fairness behaviors still depend on configured heuristics and thresholds.

## Conclusion
This project demonstrates a practical computer vision compatibility system that is both technically grounded and application-ready. The implementation integrates model-based compatibility learning, visual-rule fusion, and full-stack deployment concerns such as API timing, response sanitization, and user-facing interpretability. The hybrid recommendation design is a strong practical contribution because it prioritizes user-owned wardrobe items while preserving fallback coverage from a large reference dataset. Overall, the system is suitable as a final-year CV project with clear research value and deployment relevance.

## Further Extension
1. Quantitative evaluation suite:
- Top-k retrieval metrics (Recall@K, MRR) on controlled validation sets.
- Calibration analysis for score-to-label alignment.

2. Latency optimization:
- Smaller/faster local LLM variants and token-budget tuning.
- Parallelized preprocessing and smarter cache invalidation.

3. Better robustness for real-world uploads:
- Improved category confidence handling and uncertainty propagation.
- Enhanced crop validation for occlusion-heavy or multi-person photos.

4. Personalization:
- Learn user-specific style preferences from feedback history.
- Reweight score components per user behavior over time.

5. Production hardening:
- Dedicated observability dashboards for pipeline stages and timeout rates.
- Optional degraded operation mode for ML endpoints during DB outages.

## References
1. Han, X. et al., "Learning Fashion Compatibility with Bidirectional LSTMs," ACM MM, 2017.
2. Vasileva, M. et al., "Learning Type-Aware Embeddings for Fashion Compatibility," ECCV Workshops, 2018.
3. Polyvore Outfits Dataset (disjoint splits and compatibility tasks), public benchmark resources.
4. Ultralytics YOLOv8 Documentation (pose estimation and keypoint inference).
5. Ronneberger, O. et al., "U-Net: Convolutional Networks for Biomedical Image Segmentation," MICCAI, 2015.
6. PyTorch Documentation, Meta AI.
7. OpenCV Documentation.
8. Ollama Documentation (local LLM serving).
