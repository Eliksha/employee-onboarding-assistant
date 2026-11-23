"""Live PostgreSQL privilege and isolation-attack tests for migration 005 (roles + signed RLS scope).

Skipped unless ONBOARDAI_PG_TEST_ADMIN_DSN points at a DISPOSABLE local PostgreSQL 16 server, e.g.

    docker run -d --rm --name onboardai-roletest -e POSTGRES_PASSWORD=<random> \
        -p 127.0.0.1:55439:5432 postgres:16-alpine
    $env:ONBOARDAI_PG_TEST_ADMIN_DSN = "postgresql://postgres:<random>@127.0.0.1:55439/postgres"

The tests create a uniquely named database and two uniquely named roles, load the real Docker
schema/seed/auth SQL, run the real provisioning code, and drop only what they created.
"""
import os
import secrets
import time
from contextlib import contextmanager
from pathlib import Path

import psycopg2
import pytest
from psycopg2 import errors as pg_errors
from psycopg2.extensions import parse_dsn
from psycopg2.extras import RealDictCursor

from backend.config import ROOT, settings
from backend.services import db_roles, employee_scope

REAL_CONNECT = psycopg2.connect  # captured before the test-suite blocks PostgreSQL connections
ADMIN_DSN = os.environ.get("ONBOARDAI_PG_TEST_ADMIN_DSN", "")

pytestmark = pytest.mark.skipif(not ADMIN_DSN, reason="ONBOARDAI_PG_TEST_ADMIN_DSN not set (disposable PG only)")

SQL_DIR = ROOT / "docker" / "postgres"


def _load_migration_005():
    import importlib.util

    path = ROOT / "backend" / "migrations" / "005_least_privilege_roles.py"
    spec = importlib.util.spec_from_file_location("migration_005", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def pg():
    params = parse_dsn(ADMIN_DSN)
    assert params.get("host") in ("127.0.0.1", "localhost"), "role tests only run against a local disposable server"
    suffix = secrets.token_hex(3)
    info = {
        "host": params["host"], "port": int(params.get("port", 5432)),
        "admin_user": params["user"], "admin_password": params.get("password", ""),
        "dbname": f"onboardai_roletest_{suffix}",
        "app": f"onboardai_app_t{suffix}", "reader": f"onboardai_reader_t{suffix}",
        "app_password": secrets.token_urlsafe(24), "reader_password": secrets.token_urlsafe(24),
        "scope_secret": secrets.token_urlsafe(32),
    }
    server = REAL_CONNECT(ADMIN_DSN)
    server.autocommit = True
    with server.cursor() as cur:
        cur.execute(f'CREATE DATABASE "{info["dbname"]}"')
    try:
        loader = REAL_CONNECT(ADMIN_DSN, dbname=info["dbname"])
        with loader, loader.cursor() as cur:
            for name in ("01_schema.sql", "02_seed.sql", "03_auth_schema.sql"):
                cur.execute(Path(SQL_DIR / name).read_text(encoding="utf-8"))
        loader.close()

        # Provision twice: the second run must be a clean no-op-equivalent (idempotent).
        for _ in range(2):
            admin = REAL_CONNECT(ADMIN_DSN, dbname=info["dbname"], cursor_factory=RealDictCursor)
            plan = db_roles.build_plan(admin, app_role=info["app"], reader_role=info["reader"],
                                       app_password=info["app_password"], reader_password=info["reader_password"],
                                       scope_secret=info["scope_secret"])
            db_roles.apply_plan(admin, plan)
            admin.commit()
            admin.close()
        yield info
    finally:
        with server.cursor() as cur:
            cur.execute(f'DROP DATABASE IF EXISTS "{info["dbname"]}" WITH (FORCE)')
            for role in (info["app"], info["reader"]):
                cur.execute(f'DROP ROLE IF EXISTS "{role}"')
        server.close()


@contextmanager
def connect_as(pg, role, password=None, **kwargs):
    password = password or pg["app_password" if role == pg["app"] else "reader_password"]
    conn = REAL_CONNECT(host=pg["host"], port=pg["port"], dbname=pg["dbname"], user=role, password=password,
                        cursor_factory=RealDictCursor, **kwargs)
    try:
        yield conn
    finally:
        conn.close()


def admin_conn(pg):
    return REAL_CONNECT(ADMIN_DSN, dbname=pg["dbname"], cursor_factory=RealDictCursor)


@pytest.fixture
def as_app(pg, monkeypatch):
    """Point the real application code at the test database using the least-privilege roles."""
    monkeypatch.setattr(psycopg2, "connect", REAL_CONNECT)
    for name, value in {
        "db_backend": "postgresql", "pg_host": pg["host"], "pg_port": pg["port"], "pg_database": pg["dbname"],
        "pg_user": pg["app"], "pg_password": pg["app_password"],
        "pg_reader_user": pg["reader"], "pg_reader_password": pg["reader_password"],
        "pg_scope_secret": pg["scope_secret"], "app_env": "development",
    }.items():
        monkeypatch.setattr(settings, name, value)
    return pg


def expect_denied(conn, statement, params=None, errors=(pg_errors.InsufficientPrivilege,)):
    with pytest.raises(errors):
        with conn.cursor() as cur:
            cur.execute(statement, params)
    conn.rollback()


# ---------------------------------------------------------------- role attributes and settings
def test_roles_are_least_privilege_and_verified(pg):
    conn = admin_conn(pg)
    try:
        report = db_roles.verify(conn, pg["app"], pg["reader"])
    finally:
        conn.close()
    assert report["problems"] == []
    for role in (pg["app"], pg["reader"]):
        attrs = report["roles"][role]
        assert attrs["rolcanlogin"] and not any(
            attrs[k] for k in ("rolsuper", "rolcreaterole", "rolcreatedb", "rolbypassrls", "rolreplication"))
    assert all(report["rls"].values())


def test_reader_role_defaults_to_read_only_with_timeout(pg):
    with connect_as(pg, pg["reader"]) as conn, conn.cursor() as cur:
        cur.execute("SHOW default_transaction_read_only")
        assert cur.fetchone()["default_transaction_read_only"] == "on"
        cur.execute("SHOW statement_timeout")
        assert cur.fetchone()["statement_timeout"] == "5s"


# ---------------------------------------------------------------- APP role keeps the application working
def test_application_flows_work_with_app_and_reader_roles(as_app):
    from backend.services import auth, db, employee_db

    db.init_db()  # startup checks pass as a non-superuser
    assert db.enforce_role_policy(app_is_superuser=False) == []

    password = secrets.token_urlsafe(16)
    user_id = auth.upsert_account("pg.roles@example.com", password, "EMP001")
    user = auth.authenticate("pg.roles@example.com", password)
    assert user and user.user_id == user_id
    token, _csrf = auth.create_session(user)
    ctx = auth.resolve_session(token)
    assert ctx and ctx.user.employee_id == "EMP001"
    auth.delete_session(ctx.token_hash)
    assert auth.resolve_session(token) is None
    assert auth.set_account_active("pg.roles@example.com", False) is True

    message_id = db.save_employee_message("EMP001", "q", "a", True, [])
    assert db.get_message_owner(message_id) == (True, "EMP001")
    assert db.add_feedback(message_id, "up", "ok") > 0
    assert db.add_escalation("help", None) > 0
    assert db.recent_employee_messages("EMP001")[0]["id"] == message_id
    assert db.set_checklist_done(1, True)["done"] is True

    assert employee_db.update_employee_checklist("EMP001", 1, True)["done"] is True
    ticket = employee_db.create_employee_ticket("EMP001", "IT", "Laptop", "Screen flickers")
    assert ticket["employee_id"] == "EMP001"

    # Reads go through the reader role with row-level security.
    assert employee_db.get_employee("EMP002")["employee_id"] == "EMP002"
    assert {r["leave_type"] for r in employee_db.get_leave_balances("EMP001")}
    assert [t["ticket_id"] for t in employee_db.get_employee_tickets("EMP001")] == [ticket["ticket_id"]]
    assert employee_db.get_employee_tickets("EMP002") == []
    assert len(employee_db.get_payroll_calendar()) == 2
    checklist = employee_db.get_employee_checklist("EMP001")
    assert len(checklist) == 15 and checklist[0]["done"] is True


@pytest.mark.parametrize("statement", [
    "DELETE FROM public.employees",
    "UPDATE public.employees SET name = 'x'",
    "UPDATE public.tickets SET status = 'closed'",
    "UPDATE public.user_accounts SET email = 'x@example.com'",   # column not granted
    "DELETE FROM public.messages",
    "DELETE FROM public.user_accounts",
    "TRUNCATE public.messages",
    "DROP TABLE public.messages",
    "CREATE TABLE public.stolen (i int)",
    "ALTER TABLE public.employees ADD COLUMN x int",
    "ALTER TABLE public.employees DISABLE ROW LEVEL SECURITY",
    "INSERT INTO public.employees VALUES ('EMP9','n','e@example.com','d','2026-01-01','l')",
    "INSERT INTO public.leave_balances (employee_id, leave_type, available_days) VALUES ('EMP001','x',1)",
    "CREATE ROLE intruder",
])
def test_app_role_cannot_run_ddl_or_destructive_statements(pg, statement):
    with connect_as(pg, pg["app"]) as conn:
        expect_denied(conn, statement)


def test_app_role_cannot_escalate_itself(pg):
    with connect_as(pg, pg["app"]) as conn:
        expect_denied(conn, f'ALTER ROLE "{pg["app"]}" SUPERUSER')
        expect_denied(conn, f'ALTER ROLE "{pg["app"]}" BYPASSRLS')


# ---------------------------------------------------------------- READER role
@pytest.mark.parametrize("table", ["user_accounts", "user_sessions", "messages", "feedback", "escalations"])
def test_reader_cannot_read_sensitive_tables(pg, table):
    with connect_as(pg, pg["reader"]) as conn:
        expect_denied(conn, f"SELECT * FROM public.{table}")


def test_reader_cannot_write_even_after_disabling_read_only(pg):
    with connect_as(pg, pg["reader"]) as conn:
        expect_denied(conn, "INSERT INTO public.tickets (employee_id, category, subject, description) "
                            "VALUES ('EMP001','IT','s','d')", errors=(pg_errors.ReadOnlySqlTransaction,))
        with conn.cursor() as cur:
            cur.execute("SET default_transaction_read_only = off")
        conn.commit()
        expect_denied(conn, "INSERT INTO public.tickets (employee_id, category, subject, description) "
                            "VALUES ('EMP001','IT','s','d')")
        expect_denied(conn, "UPDATE public.leave_balances SET available_days = 99")
        expect_denied(conn, "DELETE FROM public.assets")
        expect_denied(conn, "CREATE TEMP TABLE t (i int)")
        expect_denied(conn, "CREATE TABLE public.t (i int)")


def test_row_level_security_scopes_reader_to_one_employee(as_app):
    from backend.services.postgres import postgres_readonly_connection

    for scope in ("EMP001", "EMP002"):
        with postgres_readonly_connection(scope_employee_id=scope) as conn, conn.cursor() as cur:
            for table in db_roles.RLS_TABLES:
                cur.execute(f"SELECT DISTINCT employee_id FROM public.{table}")  # no WHERE clause on purpose
                assert {r["employee_id"] for r in cur.fetchall()} <= {scope}, table
            cur.execute("SELECT count(*) AS n FROM public.payroll_calendar")   # company-wide table
            assert cur.fetchone()["n"] == 2
    with postgres_readonly_connection(scope_employee_id=None) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM public.employees")
        assert cur.fetchone()["n"] == 0                                          # no scope -> no rows


def test_fetch_readonly_timeout_row_limit_and_guard_on_postgres(as_app, monkeypatch):
    from backend.services.readonly_query import QueryTimeoutError, UnsafeQueryError, fetch_readonly

    monkeypatch.setattr(settings, "sql_agent_statement_timeout_ms", 200)
    with pytest.raises(QueryTimeoutError):
        fetch_readonly("SELECT count(*) AS n FROM checklist a, checklist b, checklist c, checklist d, "
                       "checklist e, checklist f, checklist g, checklist h")

    result = fetch_readonly("SELECT id FROM public.checklist ORDER BY id", max_rows=5)
    assert [r["id"] for r in result.rows] == [1, 2, 3, 4, 5] and result.truncated
    monkeypatch.setattr(settings, "sql_agent_max_rows", 3)
    assert len(fetch_readonly("SELECT id FROM public.checklist").rows) == 3

    for escape in ("SELECT set_config('app.current_employee', 'EMP002', true)",
                   "WITH x AS (DELETE FROM public.tickets RETURNING *) SELECT * FROM x",
                   "SELECT * FROM public.employees; SELECT 1"):
        with pytest.raises(UnsafeQueryError):
            fetch_readonly(escape, scope_employee_id="EMP001")


def test_migration_cli_verify_and_dry_run_never_print_secrets(as_app, monkeypatch, capsys):
    module = _load_migration_005()
    monkeypatch.setenv("PG_ADMIN_USER", as_app["admin_user"])
    monkeypatch.setenv("PG_ADMIN_PASSWORD", as_app["admin_password"])
    monkeypatch.setenv("ONBOARDAI_APP_DB_PASSWORD", as_app["app_password"])
    monkeypatch.setenv("ONBOARDAI_READER_DB_PASSWORD", as_app["reader_password"])
    monkeypatch.setenv("ONBOARDAI_SCOPE_SECRET", as_app["scope_secret"])
    args = ["--app-role", as_app["app"], "--reader-role", as_app["reader"]]

    assert module.main(["--verify", *args]) == 0
    assert module.main([*args, "--reset-passwords"]) == 0       # dry run: renders, executes nothing
    out = capsys.readouterr().out
    assert "DRY RUN" in out and "<redacted SCRAM-SHA-256 hash>" in out
    k_ipad, k_opad = employee_scope.hmac_pads(as_app["scope_secret"])
    for secret in (as_app["app_password"], as_app["reader_password"], as_app["admin_password"], "SCRAM-SHA-256$",
                   as_app["scope_secret"], k_ipad.hex(), k_opad.hex()):
        assert secret not in out
    # The dry run did not change the password: the old one still works.
    with connect_as(as_app, as_app["app"]) as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 AS ok")


def test_provisioning_refuses_unsafe_targets(pg):
    conn = admin_conn(pg)
    try:
        with pytest.raises(db_roles.ProvisioningError, match="target role|superuser or owns"):
            db_roles.build_plan(conn, app_role=pg["admin_user"], reader_role=pg["reader"],
                                app_password="x" * 20, reader_password="y" * 20)
        conn.rollback()
        with pytest.raises(db_roles.ProvisioningError, match="at least"):
            db_roles.build_plan(conn, app_role=f"new_app_{secrets.token_hex(2)}", reader_role=pg["reader"],
                                app_password="short", reader_password=None, scope_secret=pg["scope_secret"])
    finally:
        conn.close()


# =====================================================================================================
# Signed employee scope: direct database attacks (reader credentials + arbitrary SQL)
# =====================================================================================================
SECRET_SETTINGS = ("app.current_employee", "app.scope_expires", "app.scope_sig")


def visible_employees(cur, table="employees"):
    cur.execute(f"SELECT DISTINCT employee_id FROM public.{table}")
    return {r["employee_id"] for r in cur.fetchall()}


def signed_scope(conn, secret, employee_id, expires=None):
    """Exactly what the backend does: server connection id + HMAC signature, transaction-local."""
    with conn.cursor() as cur:
        cur.execute("SELECT onboardai_rls.connection_id() AS c")
        connection_id = cur.fetchone()["c"]
        expires = expires if expires is not None else int(time.time()) + 60
        sig = employee_scope.sign(secret, employee_id, connection_id, expires)
        cur.execute("SELECT set_config('app.current_employee', %s, true), set_config('app.scope_expires', %s, true),"
                    " set_config('app.scope_sig', %s, true)", (employee_id, str(expires), sig))
        return {"app.current_employee": employee_id, "app.scope_expires": str(expires), "app.scope_sig": sig}


def apply_settings(cur, values, local=True):
    for name, value in values.items():
        cur.execute("SELECT set_config(%s, %s, %s)", (name, value, local))


def test_valid_signed_scope_shows_exactly_one_employee(pg):
    for employee in ("EMP001", "EMP002"):
        with connect_as(pg, pg["reader"]) as conn:
            signed_scope(conn, pg["scope_secret"], employee)
            with conn.cursor() as cur:
                for table in db_roles.RLS_TABLES:
                    assert visible_employees(cur, table) <= {employee}, table
                assert visible_employees(cur) == {employee}


@pytest.mark.parametrize("attack", [
    ["SET app.current_employee = 'EMP002'"],
    ["SET LOCAL app.current_employee = 'EMP002'"],
    ["SELECT set_config('app.current_employee', 'EMP002', false)"],
    ["SELECT \"set_config\"('app.current_employee', 'EMP002', true)"],
    ["SELECT pg_catalog.set_config('app.current_employee', 'EMP002', true)"],
    ["SELECT U&\"set\\005fconfig\"('app.current_employee', 'EMP002', true)"],
    ["SET app.current_employee = 'EMP002'", "SET app.scope_expires = '9999999999'",
     "SET app.scope_sig = '" + "0" * 64 + "'"],
    ["SET app.current_employee = 'EMP002'", "SET app.scope_expires = '1'", "SET app.scope_sig = '" + "a" * 64 + "'"],
    ["SET app.current_employee = 'EMP002'", "SET app.scope_sig = 'not-hex'"],
    ["SET app.current_employee = 'EMP002'''"],
])
def test_unsigned_or_forged_scope_shows_no_employee_rows(pg, attack):
    with connect_as(pg, pg["reader"]) as conn, conn.cursor() as cur:
        for statement in attack:
            cur.execute(statement)
        for table in db_roles.RLS_TABLES:
            assert visible_employees(cur, table) == set(), (attack, table)
        cur.execute("SELECT onboardai_rls.current_employee() AS e")
        assert cur.fetchone()["e"] is None


@pytest.mark.parametrize("tamper", [
    "SET LOCAL app.current_employee = 'EMP002'",
    "SELECT set_config('app.current_employee', 'EMP002', true)",
    "SELECT \"set_config\"('app.current_employee', 'EMP002', true)",
    "SET LOCAL app.scope_expires = '9999999999'",
])
def test_tampering_with_a_valid_scope_revokes_access_instead_of_widening_it(pg, tamper):
    with connect_as(pg, pg["reader"]) as conn:
        signed_scope(conn, pg["scope_secret"], "EMP001")
        with conn.cursor() as cur:
            assert visible_employees(cur) == {"EMP001"}
            cur.execute(tamper)
            for table in db_roles.RLS_TABLES:
                assert "EMP002" not in visible_employees(cur, table), (tamper, table)
            assert visible_employees(cur) == set()


def test_signed_scope_for_another_connection_cannot_be_replayed(pg):
    with connect_as(pg, pg["reader"]) as victim, connect_as(pg, pg["reader"]) as attacker:
        stolen = signed_scope(victim, pg["scope_secret"], "EMP002")   # e.g. read from pg_stat_activity
        with victim.cursor() as cur:
            assert visible_employees(cur) == {"EMP002"}                # valid on its own connection
        with attacker.cursor() as cur:
            apply_settings(cur, stolen)
            for table in db_roles.RLS_TABLES:
                assert visible_employees(cur, table) == set(), table
            apply_settings(cur, stolen, local=False)                   # session-level copy as well
            assert visible_employees(cur) == set()


def test_expired_or_overlong_signatures_are_rejected(pg):
    now = int(time.time())
    for expires in (now - 5, now + employee_scope.MAX_SCOPE_TTL_SECONDS + 120):
        with connect_as(pg, pg["reader"]) as conn:
            signed_scope(conn, pg["scope_secret"], "EMP001", expires=expires)
            with conn.cursor() as cur:
                assert visible_employees(cur) == set(), expires


def test_signature_made_with_a_wrong_secret_is_rejected(pg):
    with connect_as(pg, pg["reader"]) as conn:
        signed_scope(conn, "an-attacker-guess-of-the-secret-0123456789", "EMP002")
        with conn.cursor() as cur:
            assert visible_employees(cur) == set()


def test_scope_is_transaction_local(pg):
    with connect_as(pg, pg["reader"]) as conn:
        signed_scope(conn, pg["scope_secret"], "EMP001")
        conn.rollback()
        with conn.cursor() as cur:
            assert visible_employees(cur) == set()


# ---------------------------------------------------------------- the secret and the verifier
@pytest.mark.parametrize("role_key", ["reader", "app"])
@pytest.mark.parametrize("statement", [
    "SELECT * FROM onboardai_private.scope_key",
    "UPDATE onboardai_private.scope_key SET k_ipad = k_opad",
    "CREATE TABLE onboardai_private.x (i int)",
    "CREATE OR REPLACE FUNCTION onboardai_rls.current_employee() RETURNS text LANGUAGE sql AS 'SELECT ''EMP002'''",
    "ALTER FUNCTION onboardai_rls.current_employee() SECURITY INVOKER",
    "CREATE FUNCTION onboardai_rls.current_employee(x int) RETURNS text LANGUAGE sql AS 'SELECT ''EMP002'''",
    "ALTER POLICY onboardai_reader_t_placeholder ON public.employees USING (true)",
    "CREATE FUNCTION pg_temp.current_employee() RETURNS text LANGUAGE sql AS 'SELECT ''EMP002'''",
])
def test_roles_cannot_read_the_secret_or_replace_the_verifier(pg, role_key, statement):
    role = pg[role_key]
    statement = statement.replace("onboardai_reader_t_placeholder", f"{pg['reader']}_own_employee")
    with connect_as(pg, role) as conn:
        if role_key == "reader":
            with conn.cursor() as cur:
                cur.execute("SET default_transaction_read_only = off")
            conn.commit()
        expect_denied(conn, statement, errors=(pg_errors.InsufficientPrivilege, pg_errors.UndefinedObject))


def test_secret_material_is_not_visible_in_catalogs(pg):
    k_ipad, k_opad = employee_scope.hmac_pads(pg["scope_secret"])
    with connect_as(pg, pg["reader"]) as conn, conn.cursor() as cur:
        cur.execute("SELECT string_agg(coalesce(prosrc, ''), ' ') AS src FROM pg_proc "
                    "WHERE pronamespace = 'onboardai_rls'::regnamespace")
        source = cur.fetchone()["src"]
        assert "current_setting('app.scope_sig'" in source        # the verifier is readable ...
        for secret in (pg["scope_secret"], k_ipad.hex(), k_opad.hex()):
            assert secret not in source                          # ... but holds no key material
        cur.execute("SELECT has_schema_privilege('onboardai_private', 'USAGE') AS u")
        assert cur.fetchone()["u"] is False
    with connect_as(pg, pg["app"]) as conn:
        # The app role cannot even resolve the verifier's schema, let alone call it.
        expect_denied(conn, "SELECT onboardai_rls.current_employee()")
        expect_denied(conn, "SELECT * FROM onboardai_private.scope_key")


# ---------------------------------------------------------------- malicious SQL through the backend path
BYPASS_QUERIES = [
    "SELECT employee_id FROM employees",
    "SELECT e.employee_id FROM (SELECT \"set_config\"('app.current_employee','EMP002',true) AS s) x "
    "CROSS JOIN LATERAL (SELECT employee_id FROM employees) e",
    "WITH s AS MATERIALIZED (SELECT \"set_config\"('app.current_employee','EMP002',true) AS v) "
    "SELECT employee_id FROM employees, s",
    "SELECT employee_id FROM employees WHERE set_config('app.current_employee','EMP002',true) IS NOT NULL "
    "OR employee_id = 'EMP002'",
    "SELECT e.employee_id FROM employees e, LATERAL set_config('app.current_employee','EMP002',true) s",
    "SELECT employee_id FROM leave_balances UNION ALL SELECT employee_id FROM tickets "
    "UNION ALL SELECT employee_id FROM assets UNION ALL SELECT employee_id FROM checklist_assignments",
]


@pytest.mark.parametrize("query", BYPASS_QUERIES)
def test_database_enforces_isolation_even_if_the_validator_is_bypassed(as_app, query):
    """Run malicious SQL on the backend's real reader connection WITHOUT the validator (simulated bug)."""
    from backend.services import readonly_query

    rows = readonly_query._fetch_postgres(query, (), "EMP001", 200)
    assert all(r["employee_id"] in ("EMP001", None) for r in rows), rows
    assert not any("EMP002" in str(r) for r in rows)


@pytest.mark.parametrize("query", BYPASS_QUERIES[1:5])   # the rest is legitimate SQL
def test_validator_rejects_the_same_malicious_sql(as_app, query):
    from backend.services.readonly_query import UnsafeQueryError, fetch_readonly

    with pytest.raises(UnsafeQueryError):
        fetch_readonly(query, scope_employee_id="EMP001")


def test_emp001_never_receives_emp002_records_on_any_execution_path(as_app):
    from backend.services import employee_db
    from backend.services.readonly_query import fetch_readonly

    employee_db.create_employee_ticket("EMP002", "HR", "EMP002 confidential", "must stay private")
    # 1. data-layer functions used by the API and chat
    for fn in (employee_db.get_employee, employee_db.get_leave_balances, employee_db.get_employee_assets,
               employee_db.get_employee_checklist, employee_db.get_employee_tickets):
        assert "EMP002" not in str(fn("EMP001")), fn.__name__
    # 2. SQL-agent path with queries that ask for everybody / explicitly for EMP002
    for table in db_roles.RLS_TABLES:
        for query, params in ((f"SELECT * FROM {table}", ()),
                              (f"SELECT * FROM {table} WHERE employee_id = ?", ("EMP002",)),
                              (f"SELECT * FROM {table} WHERE employee_id <> ?", ("EMP001",))):
            rows = fetch_readonly(query, params, scope_employee_id="EMP001").rows
            assert not any("EMP002" in str(r) for r in rows), (query, rows)
    # 3. a scope-less read-only connection sees no employee data at all
    assert fetch_readonly("SELECT * FROM employees").rows == []
    # 4. company-wide reference data stays available
    assert len(fetch_readonly("SELECT * FROM payroll_calendar", scope_employee_id="EMP001").rows) == 2


def test_wrong_backend_secret_fails_closed(as_app, monkeypatch):
    from backend.services import employee_db

    monkeypatch.setattr(settings, "pg_scope_secret", "a-different-secret-than-the-database-0123456789")
    assert employee_db.get_employee("EMP001") is None
    assert employee_db.get_leave_balances("EMP001") == []


def test_verify_reports_signed_scope_state(pg):
    conn = admin_conn(pg)
    try:
        report = db_roles.verify(conn, pg["app"], pg["reader"], scope_secret=pg["scope_secret"])
        assert report["problems"] == []
        scope = report["scope"]
        assert scope["key_present"] and scope["key_matches_secret"]
        assert scope["verifier_security_definer"] and scope["verifier_search_path_pinned"]
        assert not scope[f"{pg['reader']}_can_reach_key"] and not scope[f"{pg['app']}_can_reach_key"]
        assert scope[f"{pg['reader']}_can_execute_verifier"] and not scope[f"{pg['app']}_can_execute_verifier"]
        wrong = db_roles.verify(conn, pg["app"], pg["reader"], scope_secret="x" * 40)
        assert any("does not match" in p for p in wrong["problems"])
        plan = db_roles.build_plan(conn, app_role=pg["app"], reader_role=pg["reader"], scope_secret="y" * 40)
        assert any("does NOT match" in n for n in plan.notes)                # never silently replaced
        assert not any("rotate" in s.description for s in plan.steps)
    finally:
        conn.close()
