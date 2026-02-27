# Dataset Intelligence Infrastructure (Phase 1 MVP)

Minimal FastAPI backend that discovers HuggingFace datasets and returns a ranked top-k list (default top 7) using embedding similarity.

## Features
- `POST /api/v1/datasets/rank`
- HuggingFace dataset retrieval
- Embedding-based ranking with cosine similarity
- Structured response with ranked datasets
- Health endpoint: `GET /health`

## Run locally
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Example request
```bash
curl -X POST http://localhost:8000/api/v1/datasets/rank \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Autonomous driving perception",
    "abstract": "Need multimodal dataset for object detection and segmentation",
    "top_k": 7
  }'
```

## Notes
- Primary embedder is `sentence-transformers/all-MiniLM-L6-v2`.
- If sentence-transformers cannot load, a deterministic hash fallback embedder is used so the API remains available.
