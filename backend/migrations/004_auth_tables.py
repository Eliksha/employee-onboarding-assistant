"""Migration 004: add authentication tables (user_accounts, user_sessions).

Idempotent and additive: creates the two tables if they do not exist; never alters or deletes
existing employee, ticket, checklist or chat data. Works for the configured backend
(DB_BACKEND=postgresql or sqlite). Accounts are provisioned separately with
`python -m backend.manage_accounts`.

Usage (project root):  $env:PYTHONPATH = "."; python backend/migrations/004_auth_tables.py
"""
from backend.config import settings
from backend.services import db
from backend.services.auth_schema import AUTH_TABLES, POSTGRES_DDL, SQLITE_DDL


def migrate() -> None:
    with db._conn() as con:
        if db._postgres():
            with con.cursor() as cur:
                cur.execute(POSTGRES_DDL)
        else:
            con.executescript(SQLITE_DDL)


def verify() -> list:
    with db._conn() as con:
        if db._postgres():
            rows = db._execute(con, """SELECT table_name AS name FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name IN ('user_accounts', 'user_sessions')""", all_rows=True)
        else:
            rows = db._execute(con, """SELECT name FROM sqlite_master
                WHERE type = 'table' AND name IN ('user_accounts', 'user_sessions')""", all_rows=True)
    return sorted(r["name"] for r in rows)


if __name__ == "__main__":
    migrate()
    present = verify()
    if present != sorted(AUTH_TABLES):
        raise SystemExit(f"Migration 004 failed: found {present}")
    print(f"Migration 004 completed successfully ({settings.db_backend}): {', '.join(present)}")
