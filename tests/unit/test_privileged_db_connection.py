"""Audit finding S2: the application must fail closed on a privileged (superuser / BYPASSRLS) PostgreSQL role."""
from contextlib import contextmanager

import pytest

from backend.config import ROOT, settings
from backend.services import db

SECRET = "s" * 48


@pytest.fixture(autouse=True)
def least_privilege_settings(monkeypatch):
    monkeypatch.setattr(settings, "pg_reader_user", "onboardai_reader")
    monkeypatch.setattr(settings, "pg_scope_secret", SECRET)
    monkeypatch.setattr(settings, "allow_privileged_db_connection", False)


@pytest.mark.parametrize("env", ["development", "production", "staging", ""])
@pytest.mark.parametrize("superuser, bypassrls", [(True, False), (False, True), (True, True)])
def test_privileged_role_is_refused_by_default_in_every_environment(monkeypatch, env, superuser, bypassrls):
    monkeypatch.setattr(settings, "app_env", env)
    with pytest.raises(RuntimeError, match="privileged role"):
        db.enforce_role_policy(app_is_superuser=superuser, app_bypasses_rls=bypassrls)


@pytest.mark.parametrize("env", ["production", "staging", "Production "])
def test_override_is_ignored_outside_development(monkeypatch, env):
    monkeypatch.setattr(settings, "app_env", env)
    monkeypatch.setattr(settings, "allow_privileged_db_connection", True)
    with pytest.raises(RuntimeError, match="privileged role"):
        db.enforce_role_policy(app_is_superuser=True)


def test_override_in_development_allows_with_a_warning(monkeypatch, caplog):
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "allow_privileged_db_connection", True)
    with caplog.at_level("WARNING", logger="app"):
        issues = db.enforce_role_policy(app_is_superuser=False, app_bypasses_rls=True)
    assert issues == ["the application role can bypass row-level security"]
    assert "ALLOW_PRIVILEGED_DB_CONNECTION" in caplog.text


def test_least_privilege_role_is_accepted(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    assert db.enforce_role_policy(app_is_superuser=False, app_bypasses_rls=False) == []


def test_error_message_contains_no_credentials(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "pg_password", "pw-must-not-appear-123")
    with pytest.raises(RuntimeError) as exc:
        db.enforce_role_policy(app_is_superuser=True)
    assert "pw-must-not-appear-123" not in str(exc.value) and SECRET not in str(exc.value)


def _fake_postgres(monkeypatch, role_row):
    """init_db() against a fake PostgreSQL that returns the given pg_roles row for current_user."""

    @contextmanager
    def conn():
        yield object()

    def execute(con, query, params=(), *, one=False, all_rows=False):
        if "information_schema.tables" in query:
            return [{"table_name": t} for t in db.AUTH_TABLES]
        if "pg_roles" in query:
            assert "rolbypassrls" in query and "rolsuper" in query
            return role_row
        return {"?column?": 1}

    monkeypatch.setattr(db, "_postgres", lambda: True)
    monkeypatch.setattr(db, "_conn", conn)
    monkeypatch.setattr(db, "_execute", execute)


@pytest.mark.parametrize("row", [{"rolsuper": True, "rolbypassrls": False}, {"rolsuper": False, "rolbypassrls": True}])
def test_startup_refuses_a_privileged_connection(monkeypatch, row):
    monkeypatch.setattr(settings, "app_env", "development")
    _fake_postgres(monkeypatch, row)
    with pytest.raises(RuntimeError, match="privileged role"):
        db.init_db()


def test_startup_refuses_when_role_attributes_are_unknown(monkeypatch):
    _fake_postgres(monkeypatch, None)
    with pytest.raises(RuntimeError, match="role attributes"):
        db.init_db()


def test_startup_accepts_the_least_privilege_app_role(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    _fake_postgres(monkeypatch, {"rolsuper": False, "rolbypassrls": False})
    db.init_db()


def test_compose_pins_the_override_off_for_the_backend():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    backend = compose.split("\n  backend:")[1].split("\n  frontend:")[0]
    assert 'ALLOW_PRIVILEGED_DB_CONNECTION: "false"' in backend
