from sentence_transformers import SentenceTransformer
from app.config import EMBEDDING_MODEL_NAME
import numpy as np
import logging

logger = logging.getLogger(__name__)

# ── EAGER LOAD at import time: model loads ONCE when server starts ────────────
# Not lazy — avoids 4-5s hidden load on first user request.
logger.info(f"Loading embedding model: {EMBEDDING_MODEL_NAME}")
_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
logger.info(f"Embedding model loaded. Dimension: {_model.get_sentence_embedding_dimension()}")


def get_embedding(text: str) -> np.ndarray:
    return _model.encode(text, show_progress_bar=False)


def get_embeddings(texts: list[str]) -> np.ndarray:
    """
    Batch encode texts with optimized batch_size for CPU.
    batch_size=64 balances memory vs throughput on CPU.
    normalize_embeddings=True improves cosine similarity quality.
    """
    if not texts:
        return np.array([])
    
    return _model.encode(
        texts,
        batch_size=64,
        show_progress_bar=False,
        normalize_embeddings=True,
    )