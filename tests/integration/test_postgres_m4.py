"""M4 live PostgreSQL tests: import role (migration 006), CSV import as that role, schema dictionary vs catalog.

Skipped unless ONBOARDAI_PG_TEST_ADMIN_DSN points at a DISPOSABLE local PostgreSQL 16 server (same setup as
test_postgres_roles.py). Creates a uniquely named database and three uniquely named roles; drops only those.
"""
import secrets
import shutil
from contextlib import contextmanager
from pathlib import Path

import psycopg2
import pytest
from psycopg2 import errors as pg_errors
from psycopg2.extensions import parse_dsn
from psycopg2.extras import RealDictCursor

from backend.config import ROOT, settings
from backend.services import csv_import, db_roles, employee_db, schema_dictionary
from tests.integration.test_postgres_roles import ADMIN_DSN, REAL_CONNECT, SQL_DIR

pytestmark = pytest.mark.skipif(not ADMIN_DSN, reason="ONBOARDAI_PG_TEST_ADMIN_DSN not set (disposable PG only)")
CSV_DIR = ROOT / "data" / "csv"


@pytest.fixture(scope="module")
def pg():
    params = parse_dsn(ADMIN_DSN)
    assert params.get("host") in ("127.0.0.1", "localhost"), "M4 tests only run against a local disposable server"
    suffix = secrets.token_hex(3)
    info = {"host": params["host"], "port": int(params.get("port", 5432)), "dbname": f"onboardai_m4test_{suffix}",
            "app": f"onboardai_app_m{suffix}", "reader": f"onboardai_reader_m{suffix}",
            "importer": f"onboardai_importer_m{suffix}",
            "app_password": secrets.token_urlsafe(24), "reader_password": secrets.token_urlsafe(24),
            "importer_password": secrets.token_urlsafe(24), "scope_secret": secrets.token_urlsafe(32)}
    server = REAL_CONNECT(ADMIN_DSN)
    server.autocommit = True
    with server.cursor() as cur:
        cur.execute(f'CREATE DATABASE "{info["dbname"]}"')
    try:
        loader = REAL_CONNECT(ADMIN_DSN, dbname=info["dbname"])
        with loader, loader.cursor() as cur:
            for path in sorted(Path(SQL_DIR).glob("*.sql")):   # the full fresh-install schema (01-04)
                cur.execute(path.read_text(encoding="utf-8"))
        loader.close()
        admin = REAL_CONNECT(ADMIN_DSN, dbname=info["dbname"], cursor_factory=RealDictCursor)
        db_roles.apply_plan(admin, db_roles.build_plan(
            admin, app_role=info["app"], reader_role=info["reader"], app_password=info["app_password"],
            reader_password=info["reader_password"], scope_secret=info["scope_secret"]))
        admin.commit()
        for _ in range(2):  # migration 006 twice: idempotent
            db_roles.apply_plan(admin, db_roles.build_import_plan(
                admin, import_role=info["importer"], password=info["importer_password"],
                app_role=info["app"], reader_role=info["reader"]))
            admin.commit()
        admin.close()
        yield info
    finally:
        with server.cursor() as cur:
            cur.execute(f'DROP DATABASE IF EXISTS "{info["dbname"]}" WITH (FORCE)')
            for role in (info["app"], info["reader"], info["importer"]):
                cur.execute(f'DROP ROLE IF EXISTS "{role}"')
        server.close()


@contextmanager
def connect_as(pg, role, **kwargs):
    password = {pg["app"]: pg["app_password"], pg["reader"]: pg["reader_password"],
                pg["importer"]: pg["importer_password"]}[role]
    conn = REAL_CONNECT(host=pg["host"], port=pg["port"], dbname=pg["dbname"], user=role, password=password, **kwargs)
    try:
        yield conn
    finally:
        conn.close()


def admin(pg):
    return REAL_CONNECT(ADMIN_DSN, dbname=pg["dbname"], cursor_factory=RealDictCursor)


def snapshot(pg):
    conn = admin(pg)
    try:
        with conn.cursor() as cur:
            out = {}
            for t in ("employees", "checklist", "payroll_calendar", "leave_balances", "assets", "checklist_assignments"):
                cur.execute(f"SELECT * FROM {t} ORDER BY 1, 2")
                out[t] = [tuple(r.values()) for r in cur.fetchall()]
            return out
    finally:
        conn.close()


def import_as_importer(pg, directory, apply):
    with connect_as(pg, pg["importer"]) as conn:
        report = csv_import.run_import(conn, directory, apply=apply, postgres=True)
        conn.commit() if report.applied and report.ok else conn.rollback()
        return report


def expect_denied(conn, statement, errors=(pg_errors.InsufficientPrivilege,)):
    with pytest.raises(errors):
        with conn.cursor() as cur:
            cur.execute(statement)
    conn.rollback()


# ---------------------------------------------------------------- import role
def test_import_role_is_least_privilege_and_verified(pg):
    conn = admin(pg)
    try:
        report = db_roles.verify_import_role(conn, pg["importer"], pg["app"], pg["reader"])
        assert report["problems"] == [], report["problems"]
        assert report["privileges"]["checklist_assignments"] == ["SELECT", "INSERT"]
        assert report["privileges"]["tickets"] == [] and report["privileges"]["user_accounts"] == []
        assert db_roles.verify(conn, pg["app"], pg["reader"], scope_secret=pg["scope_secret"])["problems"] == []
    finally:
        conn.close()


@pytest.mark.parametrize("statement", [
    "DELETE FROM employees", "TRUNCATE leave_balances", "UPDATE checklist_assignments SET done = 1",
    "SELECT * FROM user_accounts", "SELECT * FROM user_sessions", "SELECT * FROM tickets", "SELECT * FROM messages",
    "SELECT * FROM onboardai_private.scope_key", "INSERT INTO tickets (employee_id, category, subject, description) "
    "VALUES ('EMP001','x','x','x')", "CREATE TABLE public.importer_x (i int)",
    "ALTER TABLE employees DISABLE ROW LEVEL SECURITY", "UPDATE checklist SET done = 1",
])
def test_import_role_cannot_exceed_its_grants(pg, statement):
    with connect_as(pg, pg["importer"]) as conn:
        expect_denied(conn, statement, (pg_errors.InsufficientPrivilege, pg_errors.FeatureNotSupported))


@pytest.mark.parametrize("role", ["app", "reader"])
@pytest.mark.parametrize("statement", [
    "INSERT INTO employees VALUES ('EMP900','x','x900@example.com','x','2026-01-01','x')",
    "INSERT INTO leave_balances (employee_id, leave_type, available_days) VALUES ('EMP001','Bonus',1)",
    "UPDATE employees SET name = 'x'", "INSERT INTO checklist (id, phase, task) VALUES (900, 'Day 1', 'x')",
])
def test_application_and_reader_roles_gained_no_write_access(pg, role, statement):
    errors = (pg_errors.InsufficientPrivilege, pg_errors.ReadOnlySqlTransaction)
    with connect_as(pg, pg[role]) as conn:
        expect_denied(conn, statement, errors)


# ---------------------------------------------------------------- CSV import as the import role
def test_seed_csvs_are_unchanged_on_a_seeded_database_and_dry_run_writes_nothing(pg):
    before = snapshot(pg)
    report = import_as_importer(pg, CSV_DIR, apply=False)
    assert report.ok, report.errors
    assert all(r.inserted == r.updated == 0 and r.unchanged == r.rows for r in report.tables.values())
    assert snapshot(pg) == before


def test_apply_then_repeat_is_idempotent_and_isolation_still_holds(pg, tmp_path, monkeypatch):
    d = tmp_path / "csv"
    shutil.copytree(CSV_DIR, d)
    with open(d / "employees.csv", "a", encoding="utf-8") as f:
        f.write("EMP004,Isha Rao,isha.rao@example.com,Sales,2026-11-30,Pune\n")
    with open(d / "leave_balances.csv", "a", encoding="utf-8") as f:
        f.write("EMP004,Casual Leave,8\nEMP004,Sick Leave,8\n")
    with open(d / "checklist_assignments.csv", "a", encoding="utf-8") as f:
        f.write("".join(f"EMP004,{i}\n" for i in range(1, 16)))
    (d / "payroll_calendar.csv").write_text("payroll_month,payment_date,status\n2026-11,2026-11-30,processed\n"
                                            "2026-12,2026-12-31,scheduled\n2027-01,2027-01-29,scheduled\n",
                                            encoding="utf-8")
    first = import_as_importer(pg, d, apply=True)
    assert first.ok and first.applied, first.errors
    assert (first.tables["employees"].inserted, first.tables["leave_balances"].inserted,
            first.tables["checklist_assignments"].inserted, first.tables["payroll_calendar"].inserted,
            first.tables["payroll_calendar"].updated) == (1, 2, 15, 1, 1)
    after = snapshot(pg)
    second = import_as_importer(pg, d, apply=True)
    assert second.ok and all(r.inserted == r.updated == 0 for r in second.tables.values())
    assert snapshot(pg) == after

    # The running application's read path (reader role + signed scope + RLS) still isolates employees.
    monkeypatch.setattr(psycopg2, "connect", REAL_CONNECT)
    for name, value in {"db_backend": "postgresql", "pg_host": pg["host"], "pg_port": pg["port"],
                        "pg_database": pg["dbname"], "pg_user": pg["app"], "pg_password": pg["app_password"],
                        "pg_reader_user": pg["reader"], "pg_reader_password": pg["reader_password"],
                        "pg_scope_secret": pg["scope_secret"]}.items():
        monkeypatch.setattr(settings, name, value)
    assert {r["leave_type"] for r in employee_db.get_leave_balances("EMP004")} == {"Casual Leave", "Sick Leave"}
    assert [i["done"] for i in employee_db.get_employee_checklist("EMP004")] == [False] * 15
    from backend.services.readonly_query import fetch_readonly
    rows = fetch_readonly("SELECT employee_id FROM leave_balances", scope_employee_id="EMP001").rows
    assert {r["employee_id"] for r in rows} == {"EMP001"}


def test_invalid_row_rolls_back_everything_on_postgres(pg, tmp_path):
    d = tmp_path / "bad"
    shutil.copytree(CSV_DIR, d)
    with open(d / "employees.csv", "a", encoding="utf-8") as f:
        f.write("EMP005,Valid Row,valid5@example.com,Sales,2026-11-30,Pune\n")
    with open(d / "assets.csv", "a", encoding="utf-8") as f:
        f.write("AST005,EMP005,Laptop,Spare,stolen\n")
    before = snapshot(pg)
    report = import_as_importer(pg, d, apply=True)
    assert not report.ok and not report.applied
    assert snapshot(pg) == before


def test_database_error_during_apply_rolls_back(pg, tmp_path, monkeypatch):
    d = tmp_path / "dberr"
    d.mkdir()
    (d / "employees.csv").write_text("employee_id,name,email,department,joining_date,location\n"
                                     "EMP006,Six,six@example.com,Sales,2026-11-30,Pune\n", encoding="utf-8")
    (d / "leave_balances.csv").write_text("employee_id,leave_type,available_days\nEMP006,Casual Leave,8\n",
                                          encoding="utf-8")
    original = csv_import._Db.execute

    def fail_on_leave(self, query, params=()):
        if query.startswith('INSERT INTO "leave_balances"'):
            raise psycopg2.OperationalError("simulated failure")
        return original(self, query, params)

    monkeypatch.setattr(csv_import._Db, "execute", fail_on_leave)
    before = snapshot(pg)
    with connect_as(pg, pg["importer"]) as conn:
        with pytest.raises(psycopg2.OperationalError):
            csv_import.run_import(conn, d, apply=True, postgres=True)
        conn.rollback()
    assert snapshot(pg) == before


def test_cli_refuses_a_superuser(pg, monkeypatch, capsys):
    from scripts import import_csv

    params = parse_dsn(ADMIN_DSN)
    monkeypatch.setattr(psycopg2, "connect", REAL_CONNECT)
    for name, value in {"db_backend": "postgresql", "pg_host": pg["host"], "pg_port": pg["port"],
                        "pg_database": pg["dbname"], "pg_user": pg["app"], "pg_reader_user": pg["reader"]}.items():
        monkeypatch.setattr(settings, name, value)
    monkeypatch.setenv("ONBOARDAI_IMPORT_DB_USER", params["user"])
    monkeypatch.setenv("ONBOARDAI_IMPORT_DB_PASSWORD", params["password"])
    assert import_csv.main([str(CSV_DIR)]) == 2
    assert "superuser" in capsys.readouterr().out


def test_cli_dry_run_as_the_import_role(pg, monkeypatch, capsys):
    from scripts import import_csv

    monkeypatch.setattr(psycopg2, "connect", REAL_CONNECT)
    for name, value in {"db_backend": "postgresql", "pg_host": pg["host"], "pg_port": pg["port"],
                        "pg_database": pg["dbname"], "pg_user": pg["app"], "pg_reader_user": pg["reader"]}.items():
        monkeypatch.setattr(settings, name, value)
    monkeypatch.setenv("ONBOARDAI_IMPORT_DB_USER", pg["importer"])
    monkeypatch.setenv("ONBOARDAI_IMPORT_DB_PASSWORD", pg["importer_password"])
    assert import_csv.main([str(CSV_DIR)]) == 0
    assert "DRY RUN" in capsys.readouterr().out


# ---------------------------------------------------------------- schema dictionary
def test_schema_dictionary_matches_the_postgresql_catalog(pg):
    conn = admin(pg)
    try:
        actual = schema_dictionary.introspect(conn)
    finally:
        conn.close()
    assert schema_dictionary.diff(schema_dictionary.tables(), actual) == []
