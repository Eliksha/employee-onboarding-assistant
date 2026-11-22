"""Database-aware /health endpoint (Local Improvement 3). Isolated SQLite; PostgreSQL is simulated."""
import logging
import re
from pathlib import Path

import psycopg2
import pytest
from fastapi.testclient import TestClient

from backend.config import ROOT, settings
from backend.main import DATABASE_UNAVAILABLE, app
from backend.services import db, postgres

HEALTHY = {"status": "ok", "database": "ok"}
UNAVAILABLE = {"status": "unavailable", "database": "unavailable", "detail": DATABASE_UNAVAILABLE}
FAKE_PW = "FakeHealthPw-9137!"


def _client():
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------- SQLite backend
def test_healthy_when_sqlite_database_is_reachable(seeded_db):
    r = _client().get("/health")
    assert r.status_code == 200 and r.json() == HEALTHY
    assert r.headers["cache-control"] == "no-store" and "x-request-id" in r.headers


def test_unavailable_when_sqlite_database_is_missing_and_no_file_is_created():
    path = Path(settings.db_path)
    assert not path.exists()
    r = _client().get("/health")
    assert r.status_code == 503 and r.json() == UNAVAILABLE
    assert not path.exists()  # read-only probe never creates the database
    assert str(path) not in r.text and path.name not in r.text


def test_health_is_public(seeded_db):
    r = _client().get("/health")  # no session cookie
    assert r.status_code == 200


# ---------------------------------------------------------------- PostgreSQL backend (simulated)
class _FakeCursor:
    def __init__(self, log):
        self.log = log

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.log.append((sql, params))

    def fetchone(self):
        return {"ok": 1}


class _FakeConnection:
    def __init__(self, log):
        self.log = log

    def cursor(self):
        return _FakeCursor(self.log)

    def commit(self):
        self.log.append(("COMMIT", None))

    def rollback(self):
        self.log.append(("ROLLBACK", None))

    def close(self):
        self.log.append(("CLOSE", None))


@pytest.fixture
def pg_settings(monkeypatch):
    monkeypatch.setattr(settings, "db_backend", "postgresql")
    monkeypatch.setattr(settings, "pg_host", "db-internal.example")
    monkeypatch.setattr(settings, "pg_user", "health_probe_user")
    monkeypatch.setattr(settings, "pg_password", FAKE_PW)


def test_healthy_when_postgres_answers_with_short_timeouts(pg_settings, monkeypatch):
    log, kwargs = [], {}

    def fake_connect(**kw):
        kwargs.update(kw)
        return _FakeConnection(log)

    monkeypatch.setattr(postgres.psycopg2, "connect", fake_connect)
    r = _client().get("/health")
    assert r.status_code == 200 and r.json() == HEALTHY
    assert kwargs["connect_timeout"] == settings.health_db_timeout_seconds == 3
    assert ("SET statement_timeout = %s", (3000,)) in log and any("SELECT 1" in sql for sql, _ in log)
    assert ("CLOSE", None) in log  # connection always released


@pytest.mark.parametrize("failure", [
    psycopg2.OperationalError(f'connection to server at "db-internal.example" failed: password={FAKE_PW} user=health_probe_user'),
    TimeoutError("timed out"),
])
def test_unavailable_when_postgres_fails_without_leaking_details(pg_settings, monkeypatch, caplog, failure):
    def failing_connect(**kw):
        raise failure

    monkeypatch.setattr(postgres.psycopg2, "connect", failing_connect)
    with caplog.at_level(logging.INFO, logger="app"):
        r = _client().get("/health")
    assert r.status_code == 503 and r.json() == UNAVAILABLE
    logs = "\n".join(rec.getMessage() for rec in caplog.records)
    assert f"database unavailable ({type(failure).__name__})" in logs
    for secret in (FAKE_PW, "db-internal.example", "health_probe_user", "password="):
        assert secret not in r.text and secret not in logs


def test_unavailable_when_postgres_blocked_by_test_isolation(pg_settings):
    """The conftest guard makes every real PostgreSQL connection fail: /health must report 503, not crash."""
    r = _client().get("/health")
    assert r.status_code == 503 and r.json() == UNAVAILABLE


def test_other_postgres_callers_keep_the_default_connect_timeout(pg_settings, monkeypatch):
    seen = {}

    def fake_connect(**kw):
        seen.update(kw)
        return _FakeConnection([])

    monkeypatch.setattr(postgres.psycopg2, "connect", fake_connect)
    with postgres.postgres_connection():
        pass
    assert seen["connect_timeout"] == 10


def test_invalid_backend_configuration_reports_unavailable(monkeypatch):
    monkeypatch.setattr(settings, "db_backend", "oracle")
    assert db.check_database() is False


# ---------------------------------------------------------------- Docker health check consistency
def test_docker_healthcheck_uses_db_aware_endpoint_with_nested_timeouts():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    m = re.search(r"HEALTHCHECK .*--timeout=(\d+)s.*\n\s+CMD .*?/health', timeout=(\d+)\).status == 200", dockerfile)
    assert m, "Docker HEALTHCHECK must call /health and require HTTP 200 (503 => unhealthy)"
    docker_timeout, request_timeout = int(m.group(1)), int(m.group(2))
    assert settings.health_db_timeout_seconds < request_timeout < docker_timeout
