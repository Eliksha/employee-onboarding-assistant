"""Live PostgreSQL tests for the deployment-readiness batch: migration 008, HR/IT queue and shared login rate limit
as the least-privilege app role, connection pool (scope isolation, recovery), and provisioning by a NON-superuser
administrator (as on Azure Database for PostgreSQL Flexible Server).

Skipped unless ONBOARDAI_PG_TEST_ADMIN_DSN points at a DISPOSABLE local PostgreSQL 16 server (see test_postgres_roles.py).
Everything created here is uniquely named and dropped afterwards.
"""
import importlib.util
import secrets
from pathlib import Path

import psycopg2
import pytest
from psycopg2.extensions import parse_dsn
from psycopg2.extras import RealDictCursor

from backend.config import ROOT, settings
from backend.services import auth, db, db_roles, hr_queue_schema, postgres
from backend.services.readonly_query import fetch_readonly
from tests.integration.test_postgres_roles import (ADMIN_DSN, REAL_CONNECT, SQL_DIR, admin_conn, as_app,  # noqa: F401
                                                   connect_as, expect_denied, pg)

pytestmark = pytest.mark.skipif(not ADMIN_DSN, reason="ONBOARDAI_PG_TEST_ADMIN_DSN not set (disposable PG only)")
PRE_008 = ("01_schema.sql", "02_seed.sql", "03_auth_schema.sql", "04_integrity.sql")


def _load(filename):
    path = ROOT / "backend" / "migrations" / filename
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def server():
    conn = REAL_CONNECT(ADMIN_DSN)
    conn.autocommit = True
    created = {"dbs": [], "roles": []}
    yield conn, created
    with conn.cursor() as cur:
        for name in created["dbs"]:
            cur.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        for role in reversed(created["roles"]):
            cur.execute(f'DROP ROLE IF EXISTS "{role}"')
    conn.close()


def _new_db(server, owner=None, files=PRE_008, as_user=None, password=None):
    conn, created = server
    name = f"onboardai_m6_{secrets.token_hex(3)}"
    with conn.cursor() as cur:
        cur.execute(f'CREATE DATABASE "{name}"' + (f' OWNER "{owner}"' if owner else ""))
    created["dbs"].append(name)
    params = parse_dsn(ADMIN_DSN)
    loader = (REAL_CONNECT(host=params["host"], port=params.get("port", 5432), dbname=name, user=as_user, password=password)
              if as_user else REAL_CONNECT(ADMIN_DSN, dbname=name))
    with loader, loader.cursor() as cur:
        for f in files:
            cur.execute((Path(SQL_DIR) / f).read_text(encoding="utf-8"))
        cur.execute("SET search_path = public")
        cur.execute("INSERT INTO escalations (question, contact_pref, status, created_at, employee_id) "
                    "VALUES ('legacy escalation', 'email', 'open', '2026-11-20T08:00:00+00:00', 'EMP001')")
    loader.close()
    return name


# ---------------------------------------------------------------- migration 008 on an existing (pre-008) database
def test_migration_008_cli_is_additive_idempotent_and_grants_the_app_role(server, monkeypatch, capsys):
    name = _new_db(server)
    role = f"onboardai_app_m6{secrets.token_hex(3)}"
    with server[0].cursor() as cur:
        cur.execute(f'CREATE ROLE "{role}" LOGIN PASSWORD %s', (secrets.token_urlsafe(24),))
    server[1]["roles"].append(role)
    params = parse_dsn(ADMIN_DSN)
    monkeypatch.setattr(psycopg2, "connect", REAL_CONNECT)
    for key, value in {"db_backend": "postgresql", "pg_host": params["host"], "pg_port": int(params.get("port", 5432)),
                       "pg_database": name, "pg_sslmode": "prefer"}.items():
        monkeypatch.setattr(settings, key, value)
    monkeypatch.setenv("PG_ADMIN_USER", params["user"])
    monkeypatch.setenv("PG_ADMIN_PASSWORD", params["password"])
    module = _load("008_hr_escalation_queue.py")
    before = [dict(r) for r in _rows(name, "SELECT * FROM escalations ORDER BY id")]
    assert module.main(["--verify", "--app-role", role]) == 1
    assert module.main(["--app-role", role]) == 0 and "DRY RUN" in capsys.readouterr().out
    assert module.main(["--apply", "--app-role", role]) == 0
    assert "Migration 008 applied: 13 DDL statements" in capsys.readouterr().out
    assert module.main(["--apply", "--app-role", role]) == 0          # idempotent
    assert module.main(["--verify", "--app-role", role]) == 0
    after = [dict(r) for r in _rows(name, "SELECT id, question, contact_pref, status, created_at, employee_id, message_id "
                                          "FROM escalations ORDER BY id")]
    assert after == [{k: r[k] for k in after[0]} for r in before]     # existing rows unchanged
    conn = admin_conn({"dbname": name})
    try:
        assert hr_queue_schema.privilege_problems(conn, role) == []
        assert hr_queue_schema.missing_objects(conn) == []
    finally:
        conn.close()


def _rows(dbname, query):
    conn = REAL_CONNECT(ADMIN_DSN, dbname=dbname, cursor_factory=RealDictCursor)
    try:
        with conn.cursor() as cur:
            cur.execute(query)
            return cur.fetchall()
    finally:
        conn.close()


# ---------------------------------------------------------------- HR/IT queue and shared limiter as the app role
def test_hr_queue_workflow_as_least_privilege_app_role(as_app):
    db._VERIFIED_CONFIGS.clear()
    hr_id = auth.upsert_account(f"hr{secrets.token_hex(3)}@novatech.example", secrets.token_urlsafe(18), None, "hr")
    mid = db.save_employee_message("EMP001", "Is a cab provided?", "Yes, after 8 PM [Handbook 3].", True, [])
    eid = db.add_escalation("Is a cab provided?", "email", employee_id="EMP001", message_id=mid, actor_user_id=None)
    item = next(i for i in db.list_escalations(status="open") if i["id"] == eid)
    assert (item["employee_name"], item["escalated_answer"]) == ("Aarav Sharma", "Yes, after 8 PM [Handbook 3].")
    db.get_escalation(eid, viewer_user_id=hr_id)
    db.update_escalation_status(eid, "in_progress", hr_id, "on it")
    result = db.update_escalation_status(eid, "resolved", hr_id, "done")
    assert [e["action"] for e in result["events"]] == ["created", "viewed", "status_changed", "status_changed"]
    with pytest.raises(db.InvalidTransition):
        db.update_escalation_status(eid, "open", hr_id)
    history = {m["id"]: m for m in db.recent_employee_messages("EMP001")}
    assert history[mid]["escalation_status"] == "resolved"


def test_app_role_cannot_rewrite_or_delete_queue_data(as_app):
    with connect_as(as_app, as_app["app"]) as conn:
        expect_denied(conn, "DELETE FROM escalations")
        expect_denied(conn, "DELETE FROM escalation_events")
        expect_denied(conn, "UPDATE escalations SET question = 'x'")
        expect_denied(conn, "UPDATE escalation_events SET note = 'x'")
        expect_denied(conn, "TRUNCATE login_failures")
    with connect_as(as_app, as_app["reader"]) as conn:
        for table in ("escalations", "escalation_events", "login_failures"):
            expect_denied(conn, f"SELECT 1 FROM {table}")


def test_shared_login_rate_limit_on_postgresql(as_app, monkeypatch):
    monkeypatch.setattr(settings, "login_rate_limit_backend", "auto")
    monkeypatch.setattr(settings, "login_max_failures_per_email", 3)
    email = f"victim{secrets.token_hex(3)}@example.com"
    replica_a, replica_b = auth.LoginLimiter(), auth.LoginLimiter()
    assert replica_a.active() is replica_a.database
    for i in range(3):
        (replica_a if i % 2 else replica_b).record_failure(email, f"203.0.113.{i}")
    assert replica_b.retry_after(email, "192.0.2.10") > 0          # counted across "instances"
    replica_a.reset_email(email)
    assert replica_b.retry_after(email, "192.0.2.10") == 0
    stored = [r["key_hash"] for r in _rows(as_app["dbname"], "SELECT key_hash FROM login_failures")]
    assert stored and all(len(k) == 64 and "@" not in k and "203.0" not in k for k in stored)


# ---------------------------------------------------------------- connection pool on a real server
@pytest.fixture
def pooled(as_app, monkeypatch):
    monkeypatch.setattr(settings, "pg_pool_enabled", True)
    monkeypatch.setattr(settings, "pg_pool_max_size", 1)               # forces reuse of the same server session
    monkeypatch.setattr(settings, "pg_pool_validate_idle_seconds", 60.0)
    postgres.close_all_pools()
    yield as_app
    postgres.close_all_pools()


def test_signed_scope_never_leaks_into_the_next_pooled_lease(pooled):
    with postgres.postgres_readonly_connection("EMP001") as conn, conn.cursor() as cur:
        cur.execute("SELECT pg_backend_pid() AS pid")
        pid = cur.fetchone()["pid"]
        cur.execute("SELECT DISTINCT employee_id FROM leave_balances")
        assert [r["employee_id"] for r in cur.fetchall()] == ["EMP001"]
    with postgres.postgres_readonly_connection(None) as conn, conn.cursor() as cur:
        cur.execute("SELECT pg_backend_pid() AS pid, current_setting('app.current_employee', true) AS emp, "
                    "current_setting('app.scope_sig', true) AS sig")
        row = cur.fetchone()
        assert row["pid"] == pid                                        # same server session reused...
        assert not row["emp"] and not row["sig"]                        # ...without the previous scope
        cur.execute("SELECT count(*) AS n FROM leave_balances")
        assert cur.fetchone()["n"] == 0                                  # RLS shows nothing without a scope
    rows = fetch_readonly("SELECT employee_id FROM leave_balances", scope_employee_id="EMP002").rows
    assert rows and {r["employee_id"] for r in rows} == {"EMP002"}


def test_session_settings_are_reset_between_leases(pooled):
    with postgres.postgres_connection() as conn, conn.cursor() as cur:
        cur.execute("SET statement_timeout = '7s'")   # distinctive; a 1 ms value raced with the next statements (flaky)
        cur.execute("SELECT set_config('app.current_employee', 'EMP002', false)")
        cur.execute("PREPARE leftover AS SELECT 1")
    with postgres.postgres_connection() as conn, conn.cursor() as cur:
        cur.execute("SHOW statement_timeout")
        assert cur.fetchone()["statement_timeout"] == "10s" == f"{settings.pg_statement_timeout_ms // 1000}s"
        cur.execute("SELECT current_setting('app.current_employee', true) AS emp, "
                    "(SELECT count(*) FROM pg_prepared_statements) AS prepared")
        row = cur.fetchone()
        assert not row["emp"] and row["prepared"] == 0


def test_pool_recovers_after_the_server_kills_its_connection(pooled, monkeypatch):
    with postgres.postgres_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT pg_backend_pid() AS pid")
        pid = cur.fetchone()["pid"]
    killer = REAL_CONNECT(ADMIN_DSN)
    killer.autocommit = True
    with killer.cursor() as cur:
        cur.execute("SELECT pg_terminate_backend(%s)", (pid,))
    killer.close()
    # Within the validation window the dead connection is used once, fails and is discarded...
    with pytest.raises(psycopg2.OperationalError):
        with postgres.postgres_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
    # ...and the next lease gets a fresh session.
    with postgres.postgres_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT pg_backend_pid() AS pid")
        assert cur.fetchone()["pid"] != pid
    # With validation of idle connections, a killed connection is replaced before use (no failed request).
    monkeypatch.setattr(settings, "pg_pool_validate_idle_seconds", 0.0)
    with postgres.postgres_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT pg_backend_pid() AS pid")
        pid = cur.fetchone()["pid"]
    killer = REAL_CONNECT(ADMIN_DSN)
    killer.autocommit = True
    with killer.cursor() as cur:
        cur.execute("SELECT pg_terminate_backend(%s)", (pid,))
    killer.close()
    with postgres.postgres_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 AS ok")
        assert cur.fetchone()["ok"] == 1


# ---------------------------------------------------------------- provisioning by a non-superuser administrator (Azure)
def test_non_superuser_administrator_can_provision_and_scope_works(server):
    suffix = secrets.token_hex(3)
    admin_role, admin_pw = f"azadmin_{suffix}", secrets.token_urlsafe(24)
    with server[0].cursor() as cur:
        cur.execute(f'CREATE ROLE "{admin_role}" LOGIN CREATEDB CREATEROLE PASSWORD %s', (admin_pw,))
    server[1]["roles"].append(admin_role)
    name = _new_db(server, owner=admin_role, files=PRE_008 + ("05_hr_queue.sql",), as_user=admin_role, password=admin_pw)
    app, reader = f"onboardai_app_az{suffix}", f"onboardai_reader_az{suffix}"
    server[1]["roles"] += [app, reader]
    secret = secrets.token_urlsafe(32)
    passwords = {app: secrets.token_urlsafe(24), reader: secrets.token_urlsafe(24)}
    params = parse_dsn(ADMIN_DSN)

    def as_admin():
        return REAL_CONNECT(host=params["host"], port=params.get("port", 5432), dbname=name, user=admin_role,
                            password=admin_pw, cursor_factory=RealDictCursor)

    for attempt in range(2):                                            # second run: existing roles, no superuser
        conn = as_admin()
        plan = db_roles.build_plan(conn, app_role=app, reader_role=reader, app_password=passwords[app],
                                   reader_password=passwords[reader], scope_secret=secret)
        rendered = " ".join(plan.render(conn))
        if attempt == 1:   # roles exist: attributes are not restated (PostgreSQL 16 refuses that for non-superusers)
            assert "NOSUPERUSER" not in rendered and "NOBYPASSRLS" not in rendered and "NOREPLICATION" not in rendered
        db_roles.apply_plan(conn, plan)
        conn.commit()
        conn.close()
    conn = as_admin()
    try:
        report = db_roles.verify(conn, app, reader, scope_secret=secret)
        assert report["problems"] == [], report["problems"]
        with conn.cursor() as cur:
            cur.execute("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
            assert cur.fetchone()["rolsuper"] is False
            cur.execute("SELECT pg_has_role(current_user, %s, 'USAGE') AS member", (reader,))
            assert cur.fetchone()["member"] is True                       # the narrow grant that replaces pg_read_all_stats
            cur.execute("SELECT pg_has_role(current_user, 'pg_read_all_stats', 'USAGE') AS stats")
            assert cur.fetchone()["stats"] is False
    finally:
        conn.close()
    # End to end: the reader sees exactly the signed employee's rows through RLS.
    reader_conn = REAL_CONNECT(host=params["host"], port=params.get("port", 5432), dbname=name, user=reader,
                               password=passwords[reader], cursor_factory=RealDictCursor)
    try:
        import time

        from backend.services import employee_scope
        with reader_conn.cursor() as cur:
            cur.execute("SELECT onboardai_rls.connection_id() AS cid")
            cid = cur.fetchone()["cid"]
            expires = int(time.time()) + 60
            sig = employee_scope.sign(secret, "EMP003", cid, expires)
            cur.execute("SELECT set_config('app.current_employee', 'EMP003', true), "
                        "set_config('app.scope_expires', %s, true), set_config('app.scope_sig', %s, true)",
                        (str(expires), sig))
            cur.execute("SELECT DISTINCT employee_id FROM leave_balances")
            assert [r["employee_id"] for r in cur.fetchall()] == ["EMP003"]
    finally:
        reader_conn.close()
