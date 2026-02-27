from __future__ import annotations

import hashlib
from typing import Iterable, List


class Embedder:
    def encode(self, texts: Iterable[str]) -> List[List[float]]:
        raise NotImplementedError


class SentenceTransformerEmbedder(Embedder):
    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2") -> None:
        from sentence_transformers import SentenceTransformer  # lazy import

        self._model = SentenceTransformer(model_name)

    def encode(self, texts: Iterable[str]) -> List[List[float]]:
        vectors = self._model.encode(list(texts), normalize_embeddings=True)
        return vectors.tolist()


class HashFallbackEmbedder(Embedder):
    """Deterministic fallback for environments without model dependencies."""

    def __init__(self, dimensions: int = 64) -> None:
        self.dimensions = dimensions

    def encode(self, texts: Iterable[str]) -> List[List[float]]:
        vectors: List[List[float]] = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            vec = [0.0] * self.dimensions
            for i in range(self.dimensions):
                vec[i] = digest[i % len(digest)] / 255.0
            norm = sum(v * v for v in vec) ** 0.5
            vectors.append([v / norm for v in vec] if norm else vec)
        return vectors
