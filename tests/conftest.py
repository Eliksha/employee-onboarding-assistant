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


@pytest.fixture(autouse=True)
def fast_test_password_hasher(monkeypatch):
    """Cheaper Argon2 parameters for test speed only; production defaults are asserted in test_auth.py."""
    from argon2 import PasswordHasher

    from backend.services import auth

    test_hasher = PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1)
    monkeypatch.setattr(auth, "_hasher", test_hasher)
    monkeypatch.setattr(auth, "_DUMMY_HASH", test_hasher.hash("dummy-password-for-timing"))


@pytest.fixture(autouse=True)
def reset_login_rate_limiter():
    """The in-process login limiter must not leak failures between tests."""
    from backend.services import auth

    auth.login_limiter.clear()
    yield
    auth.login_limiter.clear()


def _load_migration(filename):
    import importlib.util

    from backend.config import ROOT

    path = ROOT / "backend" / "migrations" / filename
    spec = importlib.util.spec_from_file_location(f"migration_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def _seeded_template(tmp_path_factory):
    """Build once per test session: real migrations 001-004 + three accounts with random passwords.

    Each test gets its own copy of this file (see `seeded_db`), so tests stay fully isolated.
    """
    import secrets
    from types import SimpleNamespace

    from argon2 import PasswordHasher

    from backend.services import auth, db

    path = tmp_path_factory.mktemp("seed") / "template.db"
    saved = (settings.db_path, settings.db_backend, auth._hasher)
    settings.db_path, settings.db_backend = path, "sqlite"
    auth._hasher = PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1)  # test speed only
    try:
        db.init_db()
        _load_migration("001_employee_schema.py").migrate(path)
        _load_migration("002_seed_demo_data.py").seed_demo_data(path)
        _load_migration("003_employee_chat_history.py").migrate(path)
        _load_migration("004_auth_tables.py").migrate()
        spec = {
            "emp1": ("aarav.sharma@example.com", "EMP001", "employee"),
            "emp2": ("meera.iyer@example.com", "EMP002", "employee"),
            "admin": ("admin@novatech.example", None, "admin"),
        }
        created = {}
        for key, (email, employee_id, role) in spec.items():
            password = secrets.token_urlsafe(18)  # random per run, never hardcoded
            auth.upsert_account(email, password, employee_id, role)
            created[key] = SimpleNamespace(email=email, password=password, employee_id=employee_id, role=role)
    finally:
        settings.db_path, settings.db_backend, auth._hasher = saved
    return path, created


@pytest.fixture
def seeded_db(env, _seeded_template):
    """Isolated SQLite DB (private copy) with employees EMP001-EMP003, checklist, chat and auth tables."""
    import shutil

    shutil.copyfile(_seeded_template[0], settings.db_path)
    return settings.db_path


@pytest.fixture
def accounts(seeded_db, _seeded_template):
    """Test accounts (emp1=EMP001, emp2=EMP002, admin) present in this test's database copy."""
    return _seeded_template[1]


def login(client, account):
    """Sign in through the real endpoint; keep the CSRF token as a default header like the SPA does."""
    r = client.post("/auth/login", json={"email": account.email, "password": account.password})
    assert r.status_code == 200, r.text
    client.headers["X-CSRF-Token"] = r.json()["csrf_token"]
    return r


@pytest.fixture
def app_client(accounts):
    from fastapi.testclient import TestClient

    from backend.main import app

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


@pytest.fixture
def emp1_client(app_client, accounts):
    login(app_client, accounts["emp1"])
    return app_client


@pytest.fixture
def admin_client(app_client, accounts):
    login(app_client, accounts["admin"])
    return app_client


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "db_path", tmp_path / "test.db")
    monkeypatch.setattr(settings, "index_dir", tmp_path / "index")
    monkeypatch.setattr(embeddings, "embed_texts", fake_embed)
    retriever.reset()
    yield settings
    retriever.reset()
