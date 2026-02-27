from __future__ import annotations

from functools import lru_cache

from fastapi import FastAPI, HTTPException

from .embeddings import HashFallbackEmbedder, SentenceTransformerEmbedder
from .models import ProjectQuery, RankingResponse
from .ranking import rank_datasets
from .retrieval import search_huggingface_datasets

app = FastAPI(title="Dataset Intelligence Infrastructure", version="0.1.0")


@lru_cache(maxsize=1)
def get_embedder():
    try:
        return SentenceTransformerEmbedder()
    except Exception:
        return HashFallbackEmbedder()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/datasets/rank", response_model=RankingResponse)
def rank_endpoint(payload: ProjectQuery) -> RankingResponse:
    query = f"{payload.title}. {payload.abstract}"

    try:
        datasets = search_huggingface_datasets(query=query, limit=50)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Dataset retrieval failed: {exc}") from exc

    if not datasets:
        return RankingResponse(query=query, total_candidates=0, ranked=[])

    ranked = rank_datasets(query=query, datasets=datasets, embedder=get_embedder(), top_k=payload.top_k)
    return RankingResponse(query=query, total_candidates=len(datasets), ranked=ranked)
