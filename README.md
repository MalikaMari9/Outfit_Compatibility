# OutfitCompatibility

Computer-vision outfit compatibility system with:
- `Mix & Match` pair scoring (`top + bottom` or full-body auto split)
- `Glow Up` recommendation from wardrobe with Polyvore fallback
- optional Ollama style explanations
- admin report moderation backed by MongoDB

## Stack
- Frontend: React + Vite + TypeScript (`frontend/wardo-hub-main`)
- Backend: Node.js + Express + MongoDB (`backend`)
- CV pipeline: Python + PyTorch (`services/pipeline`)
- Optional LLM: Ollama (local)

## Project Layout
- `backend/`: API, auth, Mongo models/controllers
- `frontend/wardo-hub-main/`: user/admin UI
- `services/pipeline/`: Python inference scripts + configs
- `assets/models/`: model checkpoints used by pipeline
- `assets/data/polyvore_outfits/`: Polyvore metadata/images
- `runtime/`: caches, temp files, processed outputs

## Prerequisites
- Node.js 18+
- Python 3.10+
- MongoDB (Atlas or local)
- (Optional) Ollama for explanation generation

## Environment Setup

### 1) Backend env
```powershell
cd backend
Copy-Item .env.example .env
```

Set required values in `backend/.env`:
- `DB_LINK`
- `HTTP_PORT`
- `JWT_SECRET`

Optional values:
- `PYTHON_BIN`, `PIPELINE_TIMEOUT_MS`, `RECOMMEND_TIMEOUT_MS`, `MAX_UPLOAD_MB`, `OLLAMA_HOST`

### 2) Frontend env
```powershell
cd frontend/wardo-hub-main
Copy-Item .env.example .env
```

Default frontend API target is:
- `VITE_API_URL=http://localhost:8001`

### 3) Python pipeline deps
```powershell
cd services/pipeline
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
deactivate
```

Recommended:
- point backend `PYTHON_BIN` to this venv python in `backend/.env`  
  Example (Windows): `PYTHON_BIN=services/pipeline/.venv/Scripts/python.exe`

## Required Model/Data Files

Expected model files under `assets/models/`:
- `compat_top_bottom.pt`
- `A_best_pattern_clean_colab.pt`
- `B_best_category_tempered.pt`
- `B_class_mapping_tempered.csv`
- `yolov8n-pose.pt`

Expected Polyvore data root:
- `assets/data/polyvore_outfits/`

Note:
- this repo `.gitignore` is configured to keep large binaries/dataset images out of git by default.

## Run (Development)

Open 2 terminals minimum.

### Terminal A: Backend
```powershell
cd backend
npm install
npm run dev
```

### Terminal B: Frontend
```powershell
cd frontend/wardo-hub-main
npm install
npm run dev
```

Frontend URL:
- `http://localhost:5173`

### Optional Terminal C: Ollama
```powershell
ollama pull qwen2.5:1.5b
ollama serve
```

## Health Checks
```powershell
Invoke-RestMethod http://localhost:8001/health
Invoke-RestMethod http://localhost:8001/health/ollama
```

## Pre-Push Checklist
- Confirm secrets are not staged (`.env` stays local).
- Confirm large runtime/data artifacts are ignored.
- Validate backend syntax:
```powershell
node --check backend/app.js
node --check backend/route.js
```
- Validate frontend build:
```powershell
npm run -s build --prefix frontend/wardo-hub-main
```

## Dataset Notice
- DeepFashion and Polyvore are external datasets with their own licenses/terms.
- Do not redistribute raw dataset files unless your usage rights allow it.
