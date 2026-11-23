"""Static checks of the least-privilege grant map against the schema and the application's SQL.

These run without PostgreSQL. Live privilege behaviour is in tests/integration/test_postgres_roles.py.
"""
import importlib.util
import re

from backend.config import ROOT
from backend.services import db_roles

SCHEMA_SQL = ((ROOT / "docker" / "postgres" / "01_schema.sql").read_text(encoding="utf-8")
              + (ROOT / "docker" / "postgres" / "03_auth_schema.sql").read_text(encoding="utf-8"))
SENSITIVE_TABLES = {"user_accounts", "user_sessions", "messages", "feedback", "escalations"}
# SQLite-only bootstrap statements in db.init_db (never run on PostgreSQL).
SQLITE_ONLY = {("INSERT", "checklist")}


def _schema_tables() -> dict:
    tables = {}
    for name, body in re.findall(r"CREATE TABLE (?:IF NOT EXISTS )?public\.(\w+) \((.*?)\n\);", SCHEMA_SQL, re.S):
        tables[name] = set(re.findall(r"^\s+(\w+) ", body, re.M)) - {"CONSTRAINT"}
    return tables


def _app_statements():
    """(verb, table, updated columns) for every write statement in the backend services."""
    found = []
    for path in (ROOT / "backend" / "services").glob("*.py"):
        src = path.read_text(encoding="utf-8")
        for table in re.findall(r"INSERT INTO (\w+)", src):
            found.append(("INSERT", table, ()))
        for table in re.findall(r"DELETE FROM (\w+)", src):
            found.append(("DELETE", table, ()))
        for table, assignments in re.findall(r"UPDATE (\w+) SET (.*?)\s+WHERE", src, re.S):
            found.append(("UPDATE", table, tuple(re.findall(r"(\w+)\s*=", assignments))))
    return found


def _granted(table, verb):
    for privilege, columns in db_roles.APP_PRIVILEGES.get(table, ()):
        if privilege == verb:
            return columns or "ALL"
    return None


def test_every_schema_table_is_covered_by_the_app_grant_map():
    assert set(db_roles.APP_PRIVILEGES) == set(_schema_tables())


def test_every_application_write_is_granted_and_nothing_more():
    statements = _app_statements()
    assert statements, "no SQL statements found"
    for verb, table, columns in statements:
        if (verb, table) in SQLITE_ONLY:
            continue
        granted = _granted(table, verb)
        assert granted, f"{verb} on {table} is used by the app but not granted"
        if granted != "ALL":
            assert set(columns) <= set(granted), f"UPDATE {table} columns {columns} not all granted"
    used = {(verb, table) for verb, table, _ in statements} - SQLITE_ONLY
    for table, privileges in db_roles.APP_PRIVILEGES.items():
        for privilege, _ in privileges:
            if privilege != "SELECT":
                assert (privilege, table) in used, f"{privilege} on {table} is granted but never used"


def test_app_role_has_no_destructive_privileges():
    for table, privileges in db_roles.APP_PRIVILEGES.items():
        names = {p for p, _ in privileges}
        assert names <= {"SELECT", "INSERT", "UPDATE", "DELETE"}, table
        if "DELETE" in names:
            assert table == "user_sessions"
        assert ("UPDATE", None) not in privileges, f"UPDATE on {table} must be column-scoped"
    assert "SUPERUSER" not in db_roles.ROLE_ATTRIBUTES.replace("NOSUPERUSER", "")
    for flag in ("NOSUPERUSER", "NOCREATEDB", "NOCREATEROLE", "NOREPLICATION", "NOBYPASSRLS"):
        assert flag in db_roles.ROLE_ATTRIBUTES


def test_reader_role_is_select_only_on_non_sensitive_tables():
    assert not SENSITIVE_TABLES & set(db_roles.READER_TABLES)
    assert set(db_roles.READER_TABLES) <= set(_schema_tables())
    assert db_roles.READER_ROLE_SETTINGS["default_transaction_read_only"] == "on"
    assert db_roles.READER_ROLE_SETTINGS["statement_timeout"]


def test_row_level_security_targets_employee_tables():
    tables = _schema_tables()
    assert set(db_roles.RLS_TABLES) <= set(db_roles.READER_TABLES)
    for table in db_roles.RLS_TABLES:
        assert "employee_id" in tables[table], table
    # Every reader-visible table with an employee_id column is row-level secured.
    assert {t for t in db_roles.READER_TABLES if "employee_id" in tables[t]} == set(db_roles.RLS_TABLES)


def test_identity_sequences_only_for_tables_the_app_inserts_into():
    for table in db_roles.APP_IDENTITY_COLUMNS:
        assert _granted(table, "INSERT"), table


def test_role_name_validation():
    import pytest

    for bad in ("", "Robert'); DROP", "a b", "onboardai-app", "x" * 64):
        with pytest.raises(db_roles.ProvisioningError):
            db_roles.validate_role_names(bad, "onboardai_reader")
    with pytest.raises(db_roles.ProvisioningError):
        db_roles.validate_role_names("same", "same")
    db_roles.validate_role_names("onboardai_app", "onboardai_reader")


def test_migration_005_is_a_noop_for_sqlite(capsys):
    path = ROOT / "backend" / "migrations" / "005_least_privilege_roles.py"
    spec = importlib.util.spec_from_file_location("migration_005", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.main([]) == 0
    assert "PostgreSQL only" in capsys.readouterr().out
