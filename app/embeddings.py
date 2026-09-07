from __future__ import annotations

import numpy as np

from app.config import settings

_model = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(settings.embedding_model)
    return _model


def embed_texts(texts: list[str]) -> np.ndarray:
    if not texts:
        return np.zeros((0, embedding_dim()), dtype="float32")
    model = _get_model()
    vectors = model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
    return vectors.astype("float32")


def embedding_dim() -> int:
    return _get_model().get_sentence_embedding_dimension()
