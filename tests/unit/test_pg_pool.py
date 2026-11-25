"""Connection pool and TLS settings (fake psycopg2 connections; live behaviour: tests/integration/test_postgres_m6.py)."""
import threading
import time

import psycopg2
import pytest

from backend.config import settings
from backend.services import postgres


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, query, params=None):
        if self.conn.broken:
            raise psycopg2.OperationalError("server closed the connection unexpectedly")
        self.conn.executed.append(query)

    def fetchone(self):
        return {"connection_id": "1:1", "ok": 1}


class FakeConnection:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs, self.executed, self.closed, self.broken = kwargs, [], 0, False
        self.autocommit, self.readonly, self.rollbacks, self.commits = False, None, 0, 0
        FakeConnection.instances.append(self)

    def cursor(self, *args, **kwargs):
        return FakeCursor(self)

    def rollback(self):
        if self.broken:
            raise psycopg2.InterfaceError("connection already closed")
        self.rollbacks += 1

    def commit(self):
        self.commits += 1

    def set_session(self, readonly=None):
        self.readonly = readonly

    def close(self):
        self.closed = 1


@pytest.fixture
def fake_pg(monkeypatch):
    FakeConnection.instances = []
    monkeypatch.setattr(postgres.psycopg2, "connect", lambda **kw: FakeConnection(**kw))
    monkeypatch.setattr(settings, "pg_pool_enabled", True)
    monkeypatch.setattr(settings, "pg_pool_max_size", 2)
    monkeypatch.setattr(settings, "pg_pool_timeout_seconds", 0.2)
    monkeypatch.setattr(settings, "pg_pool_validate_idle_seconds", 5.0)
    monkeypatch.setattr(settings, "pg_user", "onboardai_app")
    monkeypatch.setattr(settings, "pg_password", "app-secret")
    postgres.close_all_pools()
    yield FakeConnection
    postgres.close_all_pools()


def test_connections_are_reused_and_reset_on_return(fake_pg):
    with postgres.postgres_connection() as first:
        pass
    with postgres.postgres_connection() as second:
        pass
    assert first is second and len(fake_pg.instances) == 1
    assert first.commits == 2 and "DISCARD ALL" in first.executed     # session state reset between leases
    assert first.autocommit is False and first.readonly is None


def test_pool_is_bounded_and_times_out(fake_pg):
    held = [postgres.postgres_connection(), postgres.postgres_connection()]
    for cm in held:
        cm.__enter__()
    start = time.monotonic()
    with pytest.raises(postgres.PoolExhausted):
        with postgres.postgres_connection():
            pass
    assert time.monotonic() - start < 2 and len(fake_pg.instances) == 2
    for cm in held:
        cm.__exit__(None, None, None)
    with postgres.postgres_connection():   # a slot is free again
        pass


def test_waiting_lease_gets_a_connection_released_by_another_thread(fake_pg, monkeypatch):
    monkeypatch.setattr(settings, "pg_pool_max_size", 1)
    monkeypatch.setattr(settings, "pg_pool_timeout_seconds", 3)
    postgres.close_all_pools()
    cm = postgres.postgres_connection()
    cm.__enter__()
    threading.Timer(0.2, lambda: cm.__exit__(None, None, None)).start()
    with postgres.postgres_connection():
        pass
    assert len(fake_pg.instances) == 1


def test_connection_errors_discard_the_connection(fake_pg):
    with pytest.raises(psycopg2.OperationalError):
        with postgres.postgres_connection() as conn:
            raise psycopg2.OperationalError("terminating connection due to administrator command")
    assert conn.closed
    with postgres.postgres_connection() as fresh:
        pass
    assert fresh is not conn


def test_ordinary_errors_keep_the_connection_after_rollback(fake_pg):
    with pytest.raises(ValueError):
        with postgres.postgres_connection() as conn:
            raise ValueError("application error")
    assert not conn.closed and conn.rollbacks >= 1
    with postgres.postgres_connection() as again:
        pass
    assert again is conn


def test_idle_connections_are_validated_and_dead_ones_replaced(fake_pg, monkeypatch):
    monkeypatch.setattr(settings, "pg_pool_validate_idle_seconds", 0.0)
    with postgres.postgres_connection() as conn:
        pass
    conn.broken = True                      # e.g. the database restarted while the connection was idle
    with postgres.postgres_connection() as replacement:
        pass
    assert replacement is not conn and conn.closed and not replacement.closed


def test_connections_are_recycled_after_their_lifetime(fake_pg, monkeypatch):
    with postgres.postgres_connection() as conn:
        pass
    monkeypatch.setattr(settings, "pg_pool_max_lifetime_seconds", 1)
    monkeypatch.setattr(postgres.time, "monotonic", lambda real=time.monotonic: real() + 5)
    with postgres.postgres_connection() as newer:
        pass
    assert newer is not conn and conn.closed


def test_readonly_and_app_credentials_use_separate_pools(fake_pg, monkeypatch):
    monkeypatch.setattr(settings, "pg_reader_user", "onboardai_reader")
    monkeypatch.setattr(settings, "pg_reader_password", "reader-secret")
    monkeypatch.setattr(settings, "pg_scope_secret", "s" * 40)
    with postgres.postgres_connection() as app:
        pass
    with postgres.postgres_readonly_connection("EMP001") as reader:
        assert reader.readonly is True
    assert app is not reader and reader.kwargs["user"] == "onboardai_reader"
    # The scope was set transaction-locally, then rolled back and the session discarded before reuse.
    assert any("set_config" in q for q in reader.executed)
    assert reader.executed[-1] == "DISCARD ALL" and reader.readonly is None
    with postgres.postgres_readonly_connection(None) as again:
        assert again is reader and again.readonly is True
        assert not any("set_config" in q for q in again.executed[again.executed.index("DISCARD ALL") + 1:])


def test_pool_disabled_opens_and_closes_one_connection_per_use(fake_pg, monkeypatch):
    monkeypatch.setattr(settings, "pg_pool_enabled", False)
    with postgres.postgres_connection() as a:
        pass
    with postgres.postgres_connection() as b:
        pass
    assert a is not b and a.closed and b.closed


# ---------------------------------------------------------------- TLS
def test_tls_settings_are_passed_to_libpq(fake_pg, monkeypatch, tmp_path):
    ca = tmp_path / "ca.pem"
    ca.write_text("-----BEGIN CERTIFICATE-----\n")
    monkeypatch.setattr(settings, "pg_sslmode", "verify-full")
    monkeypatch.setattr(settings, "pg_sslrootcert", str(ca))
    with postgres.postgres_connection() as conn:
        pass
    assert conn.kwargs["sslmode"] == "verify-full" and conn.kwargs["sslrootcert"] == str(ca)


def test_default_tls_mode_is_prefer_without_root_cert(fake_pg):
    with postgres.postgres_connection() as conn:
        pass
    assert conn.kwargs["sslmode"] == "prefer" and "sslrootcert" not in conn.kwargs


@pytest.mark.parametrize("env, mode, ok", [("development", "prefer", True), ("development", "disable", True),
                                           ("production", "verify-full", True), ("production", "require", False),
                                           ("production", "verify-ca", False), ("production", "prefer", False),
                                           ("development", "bogus", False)])
def test_tls_policy_per_environment(monkeypatch, env, mode, ok):
    monkeypatch.setattr(settings, "app_env", env)
    monkeypatch.setattr(settings, "pg_sslmode", mode)
    monkeypatch.setattr(settings, "pg_sslrootcert", "")
    assert (postgres.tls_problems() == []) is ok
