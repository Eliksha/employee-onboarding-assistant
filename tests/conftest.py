import os
import re
import tempfile
import zlib

# Force SQLite before backend.config is imported, regardless of DB_BACKEND in .env.
os.environ["DB_BACKEND"] = "sqlite"
# Keep test traffic (including deliberate error tracebacks) out of the real logs/app.log.
os.environ["LOG_DIR"] = tempfile.mkdtemp(prefix="onboardai-test-logs-")

import numpy as np
import pytest

from backend.config import settings
from backend.services import embeddings, postgres, retriever


class PostgresBlockedInTests(RuntimeError):
    """Raised if any test code path tries to open a PostgreSQL connection."""


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    """Every test uses a throwaway SQLite file; PostgreSQL connections are hard-blocked."""

    def _blocked(*args, **kwargs):
        raise PostgresBlockedInTests("PostgreSQL access is blocked during tests")

    monkeypatch.setattr(settings, "db_backend", "sqlite")
    monkeypatch.setattr(settings, "db_path", tmp_path / "isolated_test.db")
    monkeypatch.setattr(postgres.psycopg2, "connect", _blocked)
    yield


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
