import re
import zlib

import numpy as np
import pytest

from backend.config import settings
from backend.services import embeddings, retriever


def fake_embed(texts):
    """Deterministic bag-of-words embedding so tests run offline with no model download."""
    out = np.zeros((len(texts), 512), dtype="float32")
    for i, t in enumerate(texts):
        for w in re.findall(r"[a-z0-9]+", t.lower()):
            out[i, zlib.crc32(w.encode()) % 512] += 1.0
    norms = np.linalg.norm(out, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return out / norms


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "db_path", tmp_path / "test.db")
    monkeypatch.setattr(settings, "index_dir", tmp_path / "index")
    monkeypatch.setattr(embeddings, "embed_texts", fake_embed)
    retriever.reset()
    yield settings
    retriever.reset()
