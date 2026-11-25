"""Local embeddings via fastembed (no API key needed)."""
import numpy as np

from backend.config import settings

_model = None


def _get_model():
    global _model
    if _model is None:
        from fastembed import TextEmbedding

        _model = TextEmbedding(model_name=settings.embed_model)
    return _model


def embed_texts(texts):
    """Return L2-normalised float32 vectors, so inner product == cosine similarity."""
    vecs = np.array(list(_get_model().embed(list(texts))), dtype="float32")
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vecs / norms
