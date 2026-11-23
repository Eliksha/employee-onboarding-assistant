"""M5 live PostgreSQL tests: migration 007 (data integrity) on a pre-M5 schema, constraints, safety, app paths.

Skipped unless ONBOARDAI_PG_TEST_ADMIN_DSN points at a DISPOSABLE local PostgreSQL 16 server. Every database
and role is uniquely named and dropped afterwards.
"""
import importlib.util
import secrets
from pathlib import Path

import psycopg2
import pytest
from psycopg2 import errors as pg_errors
from psycopg2.extensions import parse_dsn
from psycopg2.extras import RealDictCursor

from backend.config import ROOT, settings
from backend.services import db, db_integrity, db_roles, schema_dictionary
from tests.integration.test_postgres_roles import ADMIN_DSN, REAL_CONNECT, SQL_DIR

pytestmark = pytest.mark.skipif(not ADMIN_DSN, reason="ONBOARDAI_PG_TEST_ADMIN_DSN not set (disposable PG only)")
PRE_M5 = ("01_schema.sql", "02_seed.sql", "03_auth_schema.sql")
CHAT_ROWS = """
INSERT INTO messages (question, answer, found, sources, created_at, employee_id) VALUES
  ('q1', 'a1', 1, '[]', '2026-11-23T08:00:00+00:00', 'EMP001'),
  ('q2', 'a2', 0, '[]', '2026-11-23T08:01:00+00:00', 'EMP002'),
  ('legacy', 'a3', 1, '[]', '2026-11-20T08:00:00+00:00', NULL);
INSERT INTO feedback (message_id, rating, comment, created_at) VALUES (1, 'up', NULL, 'x'), (2, 'down', 'meh', 'x');
INSERT INTO escalations (question, contact_pref, status, created_at) VALUES ('old escalation', 'email', 'open', 'x');
"""


@pytest.fixture(scope="module")
def server():
    conn = REAL_CONNECT(ADMIN_DSN)
    conn.autocommit = True
    created = {"dbs": [], "roles": []}
    yield conn, created
    with conn.cursor() as cur:
        for name in created["dbs"]:
            cur.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        for role in created["roles"]:
            cur.execute(f'DROP ROLE IF EXISTS "{role}"')
    conn.close()


def make_db(server, files=PRE_M5, extra_sql=CHAT_ROWS):
    conn, created = server
    params = parse_dsn(ADMIN_DSN)
    assert params.get("host") in ("127.0.0.1", "localhost")
    name = f"onboardai_m5test_{secrets.token_hex(3)}"
    with conn.cursor() as cur:
        cur.execute(f'CREATE DATABASE "{name}"')
    created["dbs"].append(name)
    loader = REAL_CONNECT(ADMIN_DSN, dbname=name)
    with loader, loader.cursor() as cur:
        for f in files:
            cur.execute((Path(SQL_DIR) / f).read_text(encoding="utf-8"))
        if extra_sql:
            cur.execute("SET search_path = public")  # the pg_dump schema file empties search_path
            cur.execute(extra_sql)
    loader.close()
    return name


def admin(dbname):
    return REAL_CONNECT(ADMIN_DSN, dbname=dbname, cursor_factory=RealDictCursor)


def rows(dbname, query):
    conn = admin(dbname)
    try:
        with conn.cursor() as cur:
            cur.execute(query)
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def migrate(dbname):
    conn = admin(dbname)
    try:
        plan = db_integrity.build_plan(conn)
        db_roles.apply_plan(conn, plan)
        report = db_integrity.verify(conn)
        assert report["problems"] == [], report
        conn.commit()
        return len(plan.steps)
    finally:
        conn.close()


@pytest.fixture(scope="module")
def migrated(server):
    """Pre-M5 database with chat data, migrated by 007, with the 005 and 006 roles provisioned."""
    name = make_db(server)
    before = {t: rows(name, f"SELECT * FROM {t} ORDER BY 1") for t in ("messages", "feedback", "escalations")}
    steps = migrate(name)
    suffix = secrets.token_hex(3)
    info = {"dbname": name, "before": before, "steps": steps, "app": f"onboardai_app_n{suffix}",
            "reader": f"onboardai_reader_n{suffix}", "importer": f"onboardai_importer_n{suffix}",
            "app_password": secrets.token_urlsafe(24), "reader_password": secrets.token_urlsafe(24),
            "importer_password": secrets.token_urlsafe(24), "scope_secret": secrets.token_urlsafe(32)}
    server[1]["roles"] += [info["app"], info["reader"], info["importer"]]
    conn = admin(name)
    db_roles.apply_plan(conn, db_roles.build_plan(conn, app_role=info["app"], reader_role=info["reader"],
                                                  app_password=info["app_password"],
                                                  reader_password=info["reader_password"],
                                                  scope_secret=info["scope_secret"]))
    db_roles.apply_plan(conn, db_roles.build_import_plan(conn, import_role=info["importer"],
                                                         password=info["importer_password"],
                                                         app_role=info["app"], reader_role=info["reader"]))
    conn.commit()
    conn.close()
    return info


# ---------------------------------------------------------------- migration behaviour
def test_dry_run_plan_changes_nothing(server):
    name = make_db(server)
    conn = admin(name)
    try:
        plan = db_integrity.build_plan(conn)
        conn.rollback()
        assert len(plan.steps) == 13 and db_integrity.verify(conn)["problems"]
    finally:
        conn.close()
    assert not rows(name, "SELECT 1 FROM pg_constraint WHERE conname = 'feedback_message_id_fkey'")


def test_apply_is_complete_idempotent_and_preserves_data(migrated):
    assert migrated["steps"] == 13
    conn = admin(migrated["dbname"])
    try:
        assert db_integrity.build_plan(conn).steps == []          # second run: nothing to do
        assert db_integrity.verify(conn)["problems"] == []
    finally:
        conn.close()
    after = {t: rows(migrated["dbname"], f"SELECT * FROM {t} ORDER BY 1") for t in ("messages", "feedback", "escalations")}
    assert after["messages"] == migrated["before"]["messages"] and after["feedback"] == migrated["before"]["feedback"]
    assert [{k: v for k, v in r.items() if k not in ("employee_id", "message_id")} for r in after["escalations"]] \
        == migrated["before"]["escalations"]
    assert all(r["employee_id"] is None and r["message_id"] is None for r in after["escalations"])


def test_migrated_database_matches_the_schema_dictionary(migrated):
    conn = admin(migrated["dbname"])
    try:
        assert schema_dictionary.diff(schema_dictionary.tables(), schema_dictionary.introspect(conn)) == []
    finally:
        conn.close()


def test_roles_rls_and_import_role_still_verify_after_migration(migrated):
    conn = admin(migrated["dbname"])
    try:
        assert db_roles.verify(conn, migrated["app"], migrated["reader"], migrated["scope_secret"])["problems"] == []
        assert db_roles.verify_import_role(conn, migrated["importer"], migrated["app"], migrated["reader"])["problems"] == []
    finally:
        conn.close()


@pytest.mark.parametrize("statement, error", [
    ("INSERT INTO feedback (message_id, rating, created_at) VALUES (9999, 'up', 'x')", pg_errors.ForeignKeyViolation),
    ("INSERT INTO feedback (message_id, rating, created_at) VALUES (NULL, 'up', 'x')", pg_errors.NotNullViolation),
    ("INSERT INTO feedback (message_id, rating, created_at) VALUES (1, 'meh', 'x')", pg_errors.CheckViolation),
    ("INSERT INTO messages (question, answer, found, employee_id) VALUES ('q', 'a', 1, 'EMP999')",
     pg_errors.ForeignKeyViolation),
    ("INSERT INTO messages (question, answer, found, employee_id) VALUES ('q', 'a', 2, 'EMP001')", pg_errors.CheckViolation),
    ("INSERT INTO escalations (question, status, employee_id) VALUES ('q', 'open', 'EMP999')", pg_errors.ForeignKeyViolation),
    ("INSERT INTO escalations (question, status, message_id) VALUES ('q', 'open', 9999)", pg_errors.ForeignKeyViolation),
    ("INSERT INTO escalations (question, status) VALUES ('q', 'lost')", pg_errors.CheckViolation),
])
def test_constraints_are_enforced(migrated, statement, error):
    conn = admin(migrated["dbname"])
    try:
        with pytest.raises(error):
            with conn.cursor() as cur:
                cur.execute(statement)
    finally:
        conn.rollback()
        conn.close()


def test_deleting_a_message_cascades_feedback_and_detaches_escalations(migrated):
    conn = admin(migrated["dbname"])
    try:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO messages (question, answer, found, employee_id) VALUES ('d', 'd', 1, 'EMP001') RETURNING id")
            mid = cur.fetchone()["id"]
            cur.execute("INSERT INTO feedback (message_id, rating, created_at) VALUES (%s, 'up', 'x')", (mid,))
            cur.execute("INSERT INTO escalations (question, status, employee_id, message_id) VALUES ('d', 'open', 'EMP001', %s) "
                        "RETURNING id", (mid,))
            eid = cur.fetchone()["id"]
            cur.execute("DELETE FROM messages WHERE id = %s", (mid,))
            cur.execute("SELECT count(*) AS n FROM feedback WHERE message_id = %s", (mid,))
            assert cur.fetchone()["n"] == 0
            cur.execute("SELECT message_id, employee_id FROM escalations WHERE id = %s", (eid,))
            assert dict(cur.fetchone()) == {"message_id": None, "employee_id": "EMP001"}
    finally:
        conn.rollback()
        conn.close()


@pytest.mark.parametrize("bad_sql, label", [
    ("INSERT INTO feedback (message_id, rating, created_at) VALUES (9999, 'up', 'x')", "feedback without a message"),
    ("INSERT INTO feedback (message_id, rating, created_at) VALUES (1, 'meh', 'x')", "feedback with a rating other than up/down"),
    ("INSERT INTO messages (question, answer, found, employee_id) VALUES ('q', 'a', 1, 'EMP999')",
     "messages with an unknown employee_id"),
])
def test_invalid_existing_rows_block_the_migration_without_changes(server, bad_sql, label):
    name = make_db(server, extra_sql=CHAT_ROWS + bad_sql + ";")
    before = rows(name, "SELECT count(*) AS n FROM pg_constraint WHERE connamespace = 'public'::regnamespace")
    conn = admin(name)
    try:
        with pytest.raises(db_roles.ProvisioningError, match=label):
            db_integrity.build_plan(conn)
    finally:
        conn.rollback()
        conn.close()
    assert rows(name, "SELECT count(*) AS n FROM pg_constraint WHERE connamespace = 'public'::regnamespace") == before


def test_non_owner_is_refused(migrated):
    conn = REAL_CONNECT(host=parse_dsn(ADMIN_DSN)["host"], port=parse_dsn(ADMIN_DSN).get("port", 5432),
                        dbname=migrated["dbname"], user=migrated["app"], password=migrated["app_password"],
                        cursor_factory=RealDictCursor)
    try:
        with pytest.raises(db_roles.ProvisioningError, match="owner"):
            db_integrity.build_plan(conn)
    finally:
        conn.rollback()
        conn.close()


def test_application_paths_work_as_the_app_role_after_migration(migrated, monkeypatch):
    params = parse_dsn(ADMIN_DSN)
    monkeypatch.setattr(psycopg2, "connect", REAL_CONNECT)
    for key, value in {"db_backend": "postgresql", "pg_host": params["host"], "pg_port": int(params.get("port", 5432)),
                       "pg_database": migrated["dbname"], "pg_user": migrated["app"],
                       "pg_password": migrated["app_password"], "pg_reader_user": migrated["reader"],
                       "pg_reader_password": migrated["reader_password"],
                       "pg_scope_secret": migrated["scope_secret"], "app_env": "development"}.items():
        monkeypatch.setattr(settings, key, value)
    mid = db.save_employee_message("EMP001", "What is the leave policy?", "answer", True, [])
    db.add_feedback(mid, "down", None)
    eid = db.add_escalation("What is the leave policy?", None, employee_id="EMP001", message_id=mid)
    assert db.find_escalation(mid) == eid
    latest = db.recent_employee_messages("EMP001", 5)[0]
    assert (latest["id"], latest["feedback"], latest["escalated"]) == (mid, "down", True)
    with pytest.raises(psycopg2.errors.ForeignKeyViolation):
        db.add_escalation("x", None, employee_id="EMP999")


def test_migration_cli_modes(server, monkeypatch, capsys):
    name = make_db(server)
    params = parse_dsn(ADMIN_DSN)
    spec = importlib.util.spec_from_file_location("migration_007", ROOT / "backend" / "migrations" / "007_data_integrity.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(psycopg2, "connect", REAL_CONNECT)
    for key, value in {"db_backend": "postgresql", "pg_host": params["host"], "pg_port": int(params.get("port", 5432)),
                       "pg_database": name}.items():
        monkeypatch.setattr(settings, key, value)
    monkeypatch.setenv("PG_ADMIN_USER", params["user"])
    monkeypatch.setenv("PG_ADMIN_PASSWORD", params["password"])
    assert module.main(["--verify"]) == 1
    assert module.main([]) == 0 and "DRY RUN" in capsys.readouterr().out
    assert module.main(["--apply"]) == 0 and "Migration 007 applied: 13 statements" in capsys.readouterr().out
    assert module.main(["--verify"]) == 0
    assert module.main([]) == 0 and "nothing to do" in capsys.readouterr().out


def test_backend_refuses_to_start_on_a_database_without_migration_007(server, monkeypatch):
    name = make_db(server, extra_sql=None)
    params = parse_dsn(ADMIN_DSN)
    monkeypatch.setattr(psycopg2, "connect", REAL_CONNECT)
    for key, value in {"db_backend": "postgresql", "pg_host": params["host"], "pg_port": int(params.get("port", 5432)),
                       "pg_database": name, "pg_user": params["user"], "pg_password": params["password"],
                       "pg_reader_user": "", "pg_reader_password": "", "pg_scope_secret": "",
                       "app_env": "development"}.items():
        monkeypatch.setattr(settings, key, value)
    with pytest.raises(RuntimeError, match="migration 007"):
        db.init_db()
    migrate(name)
    # S2: the admin DSN is a superuser - refused by default (fail closed), allowed only by the development override.
    with pytest.raises(RuntimeError, match="privileged role"):
        db.init_db()
    monkeypatch.setattr(settings, "allow_privileged_db_connection", True)
    db.init_db()  # starts once migrated
    monkeypatch.setattr(settings, "app_env", "production")
    with pytest.raises(RuntimeError, match="privileged role"):
        db.init_db()  # the override is ignored outside development
