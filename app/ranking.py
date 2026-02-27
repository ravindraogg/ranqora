from __future__ import annotations

from typing import List

from .embeddings import Embedder
from .models import DatasetMetadata, RankedDataset


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        raise ValueError("Embedding sizes do not match")
    return sum(x * y for x, y in zip(a, b))


def rank_datasets(query: str, datasets: List[DatasetMetadata], embedder: Embedder, top_k: int = 7) -> List[RankedDataset]:
    if not datasets:
        return []

    corpus = [query] + [d.ranking_text() for d in datasets]
    embeddings = embedder.encode(corpus)

    query_emb = embeddings[0]
    scored = []
    for idx, ds in enumerate(datasets, start=1):
        score = cosine_similarity(query_emb, embeddings[idx])
        scored.append((score, ds))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        RankedDataset(dataset=ds, score=round(score, 4), rank=rank)
        for rank, (score, ds) in enumerate(scored[:top_k], start=1)
    ]
