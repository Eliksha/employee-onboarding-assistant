"""SQL-agent read-only executor: unauthorized statements, timeouts, row limits, employee scope.

Runs on isolated SQLite copies and on a fake psycopg2 connection (PostgreSQL stays blocked here;
real PostgreSQL permissions are covered by tests/integration/test_postgres_roles.py).
"""
import hashlib
import hmac
import logging
import re
import time

import pytest
from psycopg2 import errors as pg_errors

from backend.config import settings
from backend.services import db, employee_db, employee_scope, postgres, readonly_query
from backend.services.readonly_query import (
    QueryPermissionError,
    QueryTimeoutError,
    UnsafeQueryError,
    assert_select_only,
    fetch_readonly,
)

SLOW_SQLITE_QUERY = ("WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c WHERE x < 200000000) "
                     "SELECT count(*) AS n FROM c")


# ---------------------------------------------------------------- statement validation (PostgreSQL parser)
@pytest.mark.parametrize("query, params", [
    ("SELECT 1", 0),
    ("select leave_type, available_days from leave_balances where employee_id = ?", 1),
    ("WITH t AS (SELECT * FROM tickets WHERE employee_id = ?) SELECT count(*) FROM t", 1),
    ("SELECT ticket_id, created_at, updated_at FROM tickets;", 0),   # one trailing semicolon is fine
    ("(SELECT 1)", 0),
    ("SELECT replace(asset_name, 'x', 'y') FROM assets", 0),
    ("SELECT c.id, c.phase, c.task, ca.done FROM checklist_assignments AS ca JOIN checklist AS c "
     "ON c.id = ca.checklist_id WHERE ca.employee_id = ? ORDER BY c.id", 1),
    ("SELECT count(*) FILTER (WHERE status = 'open'), lower(subject) FROM public.tickets GROUP BY 2", 0),
    ("SELECT leave_type FROM leave_balances WHERE available_days::numeric > 1 AND leave_type LIKE 'S%'", 0),
    ("SELECT 1 -- a comment is harmless: the parser sees one SELECT", 0),
    ("SELECT CASE WHEN done = 1 THEN 'yes' END, coalesce(phase, '-') FROM checklist", 0),
    ("SELECT payroll_month FROM payroll_calendar WHERE payment_date IN (SELECT max(payment_date) FROM payroll_calendar)", 0),
])
def test_validator_accepts_allow_listed_selects(query, params):
    assert assert_select_only(query, param_count=params)


@pytest.mark.parametrize("query, reason", [
    ("", "Empty"),
    ("SELECT " + "1," * 3000 + "1", "too long"),
    ("SELEC 1", "not valid PostgreSQL"),
    # statements other than SELECT
    ("INSERT INTO tickets (employee_id) VALUES ('EMP001')", "Only SELECT"),
    ("UPDATE leave_balances SET available_days = 99", "Only SELECT"),
    ("DELETE FROM employees", "Only SELECT"),
    ("DROP TABLE employees", "Only SELECT"),
    ("TRUNCATE messages", "Only SELECT"),
    ("GRANT ALL ON employees TO PUBLIC", "Only SELECT"),
    ("SET app.current_employee = 'EMP002'", "Only SELECT"),
    ("SET LOCAL app.current_employee = 'EMP002'", "Only SELECT"),
    ("RESET ALL", "Only SELECT"),
    ("DO $$ BEGIN PERFORM 1; END $$", "Only SELECT"),
    ("CALL p()", "Only SELECT"),
    ("COPY employees TO STDOUT", "Only SELECT"),
    ("EXPLAIN ANALYZE SELECT 1", "Only SELECT"),
    ("SELECT 1; SET app.current_employee = 'EMP002'", "Exactly one statement"),
    ("SELECT 1; DROP TABLE employees", "Exactly one statement"),
    # scope-changing and other functions, in every spelling the parser resolves
    ("SELECT set_config('app.current_employee', 'EMP002', true)", "set_config"),
    ("SELECT \"set_config\"('app.current_employee', 'EMP002', true)", "set_config"),
    ("SELECT pg_catalog.set_config('app.current_employee', 'EMP002', true)", "set_config"),
    ("SELECT pg_catalog.\"set_config\"('app.current_employee', 'EMP002', true)", "set_config"),
    ("SELECT U&\"set\\005fconfig\"('app.current_employee', 'EMP002', true)", "set_config"),
    ("SELECT U&\"!0073et_config\" UESCAPE '!'('app.current_employee', 'EMP002', true)", "set_config"),
    ("SELECT \"SET_CONFIG\"('app.current_employee', 'EMP002', true)", "SET_CONFIG"),
    ("SELECT current_setting('app.current_employee')", "current_setting"),
    ("SELECT (SELECT set_config('app.current_employee', 'EMP002', true))", "set_config"),
    ("SELECT employee_id FROM employees WHERE set_config('app.current_employee', 'EMP002', true) IS NOT NULL",
     "set_config"),
    ("WITH s AS MATERIALIZED (SELECT \"set_config\"('app.current_employee','EMP002',true)) "
     "SELECT employee_id FROM employees, s", "set_config"),
    ("SELECT e.employee_id FROM employees e, LATERAL set_config('app.current_employee','EMP002',true) AS s",
     "RangeFunction"),
    ("SELECT * FROM generate_series(1, 10)", "RangeFunction"),
    ("SELECT pg_sleep(10)", "pg_sleep"),
    ("SELECT pg_read_file('/etc/passwd')", "pg_read_file"),
    ("SELECT query_to_xml('delete from tickets', true, true, '')", "query_to_xml"),
    ("SELECT nextval('tickets_ticket_id_seq')", "nextval"),
    ("SELECT onboardai_rls.current_employee()", "onboardai_rls.current_employee"),
    ("SELECT lower(name) FROM employees WHERE myschema.lower(name) = 'x'", "myschema.lower"),
    ("SELECT xmlelement(name a)", "XmlExpr"),
    ("SELECT current_user", "SQLValueFunction"),
    # data-modifying and locking constructs
    ("WITH x AS (DELETE FROM tickets RETURNING *) SELECT * FROM x", "DeleteStmt"),
    ("WITH x AS (UPDATE tickets SET status = 'x' RETURNING *) SELECT * FROM x", "UpdateStmt"),
    ("SELECT * INTO stolen FROM employees", "SELECT INTO"),
    ("SELECT * FROM tickets FOR UPDATE", "Row locking"),
    ("SELECT * FROM tickets FOR SHARE", "Row locking"),
    # tables outside the reader's allow-list
    ("SELECT * FROM user_accounts", "user_accounts"),
    ("SELECT * FROM public.user_sessions", "user_sessions"),
    ("SELECT question FROM messages", "messages"),
    ("SELECT employee_id FROM employees UNION SELECT email FROM user_accounts", "user_accounts"),
    ("SELECT query FROM pg_stat_activity", "pg_stat_activity"),
    ("SELECT * FROM pg_catalog.pg_proc", "pg_catalog"),
    ("SELECT * FROM onboardai_private.scope_key", "onboardai_private"),
    ("SELECT * FROM information_schema.tables", "information_schema"),
    ("SELECT 'set_config'::regproc", "regproc"),
    ("SELECT name::pg_catalog.regclass FROM employees", "regclass"),
    # placeholder smuggling
    ("SELECT '?' FROM employees WHERE employee_id = ?", "real parameters"),
])
def test_validator_rejects_unauthorized_statements(query, reason):
    with pytest.raises(UnsafeQueryError, match=f"(?i){re.escape(reason)}"):
        assert_select_only(query, param_count=query.count("?"))


def test_validator_requires_matching_parameter_count():
    with pytest.raises(UnsafeQueryError, match="Expected 1 parameters, got 0"):
        assert_select_only("SELECT 1 FROM employees WHERE employee_id = ?", param_count=0)


def test_rejected_statement_never_reaches_the_database(seeded_db, monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("database must not be touched")

    monkeypatch.setattr(readonly_query, "_fetch_sqlite", boom)
    for query in ("DELETE FROM messages", "SELECT \"set_config\"('app.current_employee','EMP002',true)"):
        with pytest.raises(UnsafeQueryError):
            fetch_readonly(query)


# ---------------------------------------------------------------- signed employee scope (HMAC)
SECRET = "unit-test-scope-secret-0123456789abcdef"


def test_sql_hmac_formula_matches_python_hmac():
    """The SQL verifier computes sha256(k_opad || sha256(k_ipad || msg)); it must equal hmac-sha256."""
    k_ipad, k_opad = employee_scope.hmac_pads(SECRET)
    msg = employee_scope.message("EMP001", "1234:1700000000123456", 1800000000)
    sql_style = hashlib.sha256(k_opad + hashlib.sha256(k_ipad + msg).digest()).hexdigest()
    assert sql_style == employee_scope.sign(SECRET, "EMP001", "1234:1700000000123456", 1800000000)
    assert len(k_ipad) == len(k_opad) == 64


def test_signature_binds_employee_connection_and_expiry():
    base = employee_scope.sign(SECRET, "EMP001", "10:20", 100)
    assert base != employee_scope.sign(SECRET, "EMP002", "10:20", 100)
    assert base != employee_scope.sign(SECRET, "EMP001", "11:20", 100)
    assert base != employee_scope.sign(SECRET, "EMP001", "10:20", 101)
    assert base != employee_scope.sign(SECRET + "x", "EMP001", "10:20", 100)


@pytest.mark.parametrize("bad", ["", "EMP 001", "EMP001'; --", "x" * 65, "EMP:001", None])
def test_scope_rejects_malformed_employee_ids(bad):
    with pytest.raises(employee_scope.ScopeError):
        employee_scope.sign(SECRET, bad, "1:2", 3)


def test_scope_secret_minimum_length():
    with pytest.raises(employee_scope.ScopeError):
        employee_scope.derive_key("too-short")


def test_verifier_sql_is_security_definer_with_pinned_search_path_and_no_secret():
    sql_text = employee_scope.CURRENT_EMPLOYEE_SQL
    assert "SECURITY DEFINER" in sql_text and "SET search_path = pg_catalog, pg_temp" in sql_text
    assert "onboardai_private.scope_key" in sql_text and "%(" not in sql_text
    assert "clock_timestamp()" in sql_text and "onboardai_rls.connection_id()" in sql_text
    assert employee_scope.READER_POLICY_EXPRESSION == "employee_id = (SELECT onboardai_rls.current_employee())"


# ---------------------------------------------------------------- SQLite enforcement
def test_sqlite_readonly_connection_refuses_writes_even_without_the_guard(seeded_db):
    with pytest.raises(QueryPermissionError):
        readonly_query._fetch_sqlite("UPDATE checklist_assignments SET done = 1", (), 10)
    with pytest.raises(QueryPermissionError):
        readonly_query._fetch_sqlite(
            "INSERT INTO tickets (employee_id, category, subject, description) VALUES ('EMP001','IT','s','d')", (), 10)


def test_sqlite_timeout_cancels_long_query(seeded_db, monkeypatch):
    monkeypatch.setattr(settings, "sql_agent_statement_timeout_ms", 50)
    with pytest.raises(QueryTimeoutError):
        fetch_readonly(SLOW_SQLITE_QUERY)


def test_row_limit_truncates_and_logs(seeded_db, caplog):
    with caplog.at_level(logging.WARNING, logger="app"):
        result = fetch_readonly("SELECT id FROM checklist ORDER BY id", max_rows=5)
    assert [r["id"] for r in result.rows] == [1, 2, 3, 4, 5]
    assert result.truncated is True
    assert "truncated" in caplog.text


def test_row_limit_setting_is_a_ceiling(seeded_db, monkeypatch):
    monkeypatch.setattr(settings, "sql_agent_max_rows", 3)
    result = fetch_readonly("SELECT id FROM checklist ORDER BY id", max_rows=1000)  # cannot raise the ceiling
    assert len(result.rows) == 3 and result.truncated


def test_small_results_are_not_truncated(seeded_db):
    result = fetch_readonly("SELECT leave_type FROM leave_balances WHERE employee_id = ?", ("EMP001",))
    assert result.rows and result.truncated is False


# ---------------------------------------------------------------- employee isolation in the data layer
def test_employee_reads_are_scoped_to_the_requested_employee(monkeypatch):
    calls = []

    def fake_fetch(query, params=(), *, scope_employee_id=None, max_rows=None):
        calls.append((query, tuple(params), scope_employee_id))
        return readonly_query.ReadOnlyResult(rows=[])

    monkeypatch.setattr(employee_db, "fetch_readonly", fake_fetch)
    for fn in (employee_db.get_employee, employee_db.get_leave_balances, employee_db.get_employee_assets,
               employee_db.get_employee_checklist, employee_db.get_employee_tickets):
        fn("EMP001")
    assert len(calls) == 5
    for query, params, scope in calls:
        assert scope == "EMP001", query           # row-level-security scope
        assert params == ("EMP001",), query       # and an explicit, bound WHERE filter
        assert "employee_id = ?" in query
    employee_db.get_payroll_calendar()
    assert calls[-1][2] is None                   # company-wide table, no employee scope


def test_employee_reads_return_only_that_employee(seeded_db):
    for employee_id in ("EMP001", "EMP002"):
        assert employee_db.get_employee(employee_id)["employee_id"] == employee_id
    employee_db.create_employee_ticket("EMP002", "IT", "Other employee's ticket", "Must stay private")
    assert all(t["subject"] != "Other employee's ticket" for t in employee_db.get_employee_tickets("EMP001"))
    assert [t["subject"] for t in employee_db.get_employee_tickets("EMP002")] == ["Other employee's ticket"]
    assert employee_db.get_employee("EMP999") is None


# ---------------------------------------------------------------- PostgreSQL connection settings (fake driver)
FAKE_CONNECTION_ID = "4242:1700000000000001"


class FakeCursor:
    def __init__(self, conn, name=None):
        self.conn, self.name, self.itersize = conn, name, None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, query, params=None):
        self.conn.executed.append((self.name, query, params))
        if self.conn.raise_on_execute and self.name:
            raise self.conn.raise_on_execute

    def fetchone(self):
        return {"connection_id": FAKE_CONNECTION_ID}

    def fetchmany(self, size):
        self.conn.fetch_sizes.append(size)
        return [{"id": i} for i in range(1, self.conn.available_rows + 1)][:size]


class FakeConnection:
    def __init__(self, raise_on_execute=None, available_rows=3):
        self.executed, self.fetch_sizes, self.session = [], [], {}
        self.raise_on_execute, self.available_rows = raise_on_execute, available_rows
        self.committed = self.rolled_back = self.closed = False

    def set_session(self, **kwargs):
        self.session.update(kwargs)

    def cursor(self, name=None, cursor_factory=None):
        return FakeCursor(self, name)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


@pytest.fixture
def fake_pg(monkeypatch):
    state = {"kwargs": None, "conn": FakeConnection()}

    def connect(**kwargs):
        state["kwargs"] = kwargs
        return state["conn"]

    monkeypatch.setattr(postgres.psycopg2, "connect", connect)
    monkeypatch.setattr(settings, "db_backend", "postgresql")
    monkeypatch.setattr(settings, "pg_user", "onboardai_app")
    monkeypatch.setattr(settings, "pg_password", "app-secret-value")
    monkeypatch.setattr(settings, "pg_reader_user", "onboardai_reader")
    monkeypatch.setattr(settings, "pg_reader_password", "reader-secret-value")
    monkeypatch.setattr(settings, "pg_scope_secret", SECRET)
    monkeypatch.setattr(settings, "sql_agent_statement_timeout_ms", 1234)
    return state


def test_readonly_connection_uses_reader_role_readonly_timeout_and_scope(fake_pg):
    fetch_readonly("SELECT id FROM checklist_assignments WHERE employee_id = ?", ("EMP001",),
                   scope_employee_id="EMP001")
    kwargs, conn = fake_pg["kwargs"], fake_pg["conn"]
    assert kwargs["user"] == "onboardai_reader" and kwargs["password"] == "reader-secret-value"
    assert "-c default_transaction_read_only=on" in kwargs["options"]
    assert "-c statement_timeout=1234" in kwargs["options"]
    assert conn.session == {"readonly": True}
    # 1. ask the server for this connection's id, 2. set the SIGNED scope, 3. run the query
    assert conn.executed[0][1] == "SELECT onboardai_rls.connection_id() AS connection_id"
    scope_sql, scope_params = conn.executed[1][1], conn.executed[1][2]
    assert scope_sql.count("set_config(%s, %s, true)") == 3
    employee_setting, employee, expires_setting, expires, sig_setting, signature = scope_params
    assert (employee_setting, employee, expires_setting, sig_setting) == (
        "app.current_employee", "EMP001", "app.scope_expires", "app.scope_sig")
    assert 0 < int(expires) - time.time() <= employee_scope.SCOPE_TTL_SECONDS + 1
    expected = hmac.new(employee_scope.derive_key(SECRET),
                        f"v1:EMP001:{FAKE_CONNECTION_ID}:{expires}".encode(), hashlib.sha256).hexdigest()
    assert signature == expected
    name, query, params = conn.executed[2]
    assert name == "onboardai_readonly"                      # server-side cursor
    assert query.endswith("employee_id = %s") and params == ("EMP001",)
    assert conn.rolled_back and not conn.committed and conn.closed


def test_readonly_connection_without_scope_sets_no_scope(fake_pg):
    fetch_readonly("SELECT payroll_month FROM payroll_calendar")
    executed = fake_pg["conn"].executed
    assert len(executed) == 1 and executed[0][0] == "onboardai_readonly"   # only the query itself


def test_dedicated_reader_without_scope_secret_fails_closed(fake_pg, monkeypatch):
    monkeypatch.setattr(settings, "pg_scope_secret", "")
    with pytest.raises(employee_scope.ScopeError, match="PG_SCOPE_SECRET"):
        fetch_readonly("SELECT leave_type FROM leave_balances WHERE employee_id = ?", ("EMP001",),
                       scope_employee_id="EMP001")
    assert all(call[0] != "onboardai_readonly" for call in fake_pg["conn"].executed)   # query never ran


def test_malformed_scope_is_rejected_before_any_query(fake_pg):
    with pytest.raises(employee_scope.ScopeError):
        fetch_readonly("SELECT 1 AS id", scope_employee_id="EMP001' OR '1'='1")


def test_readonly_connection_falls_back_to_app_credentials_still_readonly(fake_pg, monkeypatch):
    monkeypatch.setattr(settings, "pg_reader_user", "")
    fetch_readonly("SELECT 1 AS id", scope_employee_id="EMP001")
    kwargs = fake_pg["kwargs"]
    assert kwargs["user"] == "onboardai_app"
    # app/owner credentials are not subject to the reader policies, so no scope is signed
    assert [c[0] for c in fake_pg["conn"].executed] == ["onboardai_readonly"]
    assert "default_transaction_read_only=on" in kwargs["options"]
    assert not readonly_query.reader_is_dedicated()


def test_postgres_row_limit_fetches_at_most_limit_plus_one(fake_pg):
    fake_pg["conn"].available_rows = 50
    result = fetch_readonly("SELECT id FROM checklist", max_rows=10)
    assert fake_pg["conn"].fetch_sizes == [11]
    assert len(result.rows) == 10 and result.truncated


@pytest.mark.parametrize("error, expected", [
    (pg_errors.QueryCanceled("canceling statement due to statement timeout"), QueryTimeoutError),
    (pg_errors.InsufficientPrivilege("permission denied for table user_accounts"), QueryPermissionError),
    (pg_errors.ReadOnlySqlTransaction("cannot execute INSERT in a read-only transaction"), QueryPermissionError),
])
def test_postgres_errors_are_mapped(fake_pg, error, expected):
    fake_pg["conn"].raise_on_execute = error
    with pytest.raises(expected):
        fetch_readonly("SELECT id FROM checklist")
    assert fake_pg["conn"].rolled_back and not fake_pg["conn"].committed


def test_app_connection_has_statement_timeout(fake_pg, monkeypatch):
    monkeypatch.setattr(settings, "pg_statement_timeout_ms", 4321)
    with postgres.postgres_connection():
        pass
    assert fake_pg["kwargs"]["user"] == "onboardai_app"
    assert fake_pg["kwargs"]["options"] == "-c statement_timeout=4321"
    assert fake_pg["conn"].committed


# ---------------------------------------------------------------- API behaviour and startup policy
def test_query_timeout_returns_503_without_sql_details(emp1_client, monkeypatch):
    def slow(*args, **kwargs):
        raise QueryTimeoutError("Read-only query timed out")

    monkeypatch.setattr(readonly_query, "_fetch_sqlite", slow)
    r = emp1_client.get("/employees/EMP001/leave-balances")
    assert r.status_code == 503
    assert r.json() == {"detail": "The database took too long to respond. Please try again."}
    assert r.headers.get("Retry-After") == "5"
    assert "SELECT" not in r.text and "leave_balances" not in r.text


def test_role_policy_refuses_superuser_and_missing_reader_in_production(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "pg_reader_user", "onboardai_reader")
    monkeypatch.setattr(settings, "pg_scope_secret", SECRET)
    with pytest.raises(RuntimeError, match="superuser"):
        db.enforce_role_policy(app_is_superuser=True)
    monkeypatch.setattr(settings, "pg_reader_user", "")
    with pytest.raises(RuntimeError, match="PG_READER_USER"):
        db.enforce_role_policy(app_is_superuser=False)


@pytest.mark.parametrize("env", ["development", "production"])
@pytest.mark.parametrize("secret", ["", "short-secret"])
def test_reader_without_valid_scope_secret_refuses_to_start(monkeypatch, env, secret):
    monkeypatch.setattr(settings, "app_env", env)
    monkeypatch.setattr(settings, "pg_reader_user", "onboardai_reader")
    monkeypatch.setattr(settings, "pg_scope_secret", secret)
    with pytest.raises(RuntimeError, match="PG_SCOPE_SECRET"):
        db.enforce_role_policy(app_is_superuser=False)


def test_role_policy_only_warns_in_development(monkeypatch, caplog):
    # Missing reader role: warning only in development. A superuser needs the explicit development override.
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "pg_reader_user", "")
    monkeypatch.setattr(settings, "allow_privileged_db_connection", True)
    with caplog.at_level(logging.WARNING, logger="app"):
        issues = db.enforce_role_policy(app_is_superuser=True)
    assert len(issues) == 2 and "superuser" in caplog.text
    monkeypatch.setattr(settings, "allow_privileged_db_connection", False)
    assert len(db.enforce_role_policy(app_is_superuser=False)) == 1
    monkeypatch.setattr(settings, "pg_reader_user", "onboardai_reader")
    monkeypatch.setattr(settings, "pg_scope_secret", SECRET)
    assert db.enforce_role_policy(app_is_superuser=False) == []
