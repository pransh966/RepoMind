"""
Embeddings run locally via sentence-transformers -- deliberately, not via an
API. This means ingesting a 500-file repo costs $0 and works offline; only
the final answer-generation step needs an LLM API key. That tradeoff (cheap,
fast, local retrieval + a paid call only for the last-mile generation step)
is a real production pattern, not just a demo shortcut.
"""
from __future__ import annotations

import numpy as np

from app.config import settings

_model = None  # lazy-loaded singleton; avoids paying model-load cost on import (matters for test speed)


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(settings.embedding_model)
    return _model


def embed_texts(texts: list[str]) -> np.ndarray:
    """Return an (N, D) float32 array of L2-normalized embeddings, ready for
    cosine similarity via inner product (see vector_store.py)."""
    if not texts:
        return np.zeros((0, embedding_dim()), dtype="float32")
    model = _get_model()
    vectors = model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
    return vectors.astype("float32")


def embedding_dim() -> int:
    return _get_model().get_sentence_embedding_dimension()
