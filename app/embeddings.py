from __future__ import annotations

import numpy as np

from app.config import settings

_model = None
_dim = None


def _get_model():
    global _model
    if _model is None:
        from fastembed import TextEmbedding
        _model = TextEmbedding(model_name=settings.embedding_model)
    return _model


def embed_texts(texts: list[str]) -> np.ndarray:
    if not texts:
        return np.zeros((0, embedding_dim()), dtype="float32")
    model = _get_model()
    vectors = np.array(list(model.embed(texts)), dtype="float32")
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1
    return (vectors / norms).astype("float32")


def embedding_dim() -> int:
    global _dim
    if _dim is None:
        model = _get_model()
        probe = next(iter(model.embed(["dimension probe"])))
        _dim = len(probe)
    return _dim
