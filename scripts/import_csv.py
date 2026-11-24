"""Import HR reference data from CSV files (dry run by default). See backend/services/csv_import.py.

PostgreSQL: connects as the dedicated import role (migration 006) - never as the application, reader or
owner/superuser role (refused):
  ONBOARDAI_IMPORT_DB_USER     (default onboardai_importer)
  ONBOARDAI_IMPORT_DB_PASSWORD (environment only; from the external secrets file)
  PG_HOST / PG_PORT / PG_DATABASE from the normal settings.
SQLite (local development and tests): uses DB_PATH.

Usage (repository root):
  python -m scripts.import_csv data/csv                 # dry run: validate + report, nothing written
  python -m scripts.import_csv data/csv --apply         # one transaction; any error -> nothing written
  python -m scripts.import_csv data/csv --json report.json
Exit codes: 0 ok, 1 validation failed (nothing written), 2 refused (connection / role / setup).
"""
import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

from backend.config import settings
from backend.services import csv_import, db_roles


def _postgres_connection():
    import psycopg2

    user = os.environ.get("ONBOARDAI_IMPORT_DB_USER") or db_roles.IMPORT_ROLE
    password = os.environ.get("ONBOARDAI_IMPORT_DB_PASSWORD")
    if not password:
        raise csv_import.CsvImportError("ONBOARDAI_IMPORT_DB_PASSWORD is not set")
    if user in {settings.pg_user, settings.pg_reader_user, db_roles.APP_ROLE, db_roles.READER_ROLE} - {""}:
        raise csv_import.CsvImportError(f"Refusing to import as {user}: use the dedicated import role")
    conn = psycopg2.connect(host=settings.pg_host, port=settings.pg_port, dbname=settings.pg_database, user=user,
                            password=password, connect_timeout=10, application_name="onboardai-csv-import",
                            sslmode=settings.pg_sslmode.strip().lower() or "prefer",
                            **({"sslrootcert": settings.pg_sslrootcert.strip()} if settings.pg_sslrootcert.strip() else {}))
    with conn.cursor() as cur:
        cur.execute("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
        superuser, bypass = cur.fetchone()
    if superuser or bypass:
        conn.close()
        raise csv_import.CsvImportError(f"Refusing to import as {user}: superuser/BYPASSRLS roles are not allowed")
    return conn


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("directory", nargs="?", default="data/csv")
    parser.add_argument("--apply", action="store_true", help="write the changes (default: dry run)")
    parser.add_argument("--json", help="also write the report as JSON to this path")
    args = parser.parse_args(argv)

    postgres = settings.db_backend.strip().lower() == "postgresql"
    try:
        conn = _postgres_connection() if postgres else sqlite3.connect(str(Path(settings.db_path).resolve()))
    except csv_import.CsvImportError as exc:
        print(f"Refused: {exc}")
        return 2
    try:
        if not postgres:
            conn.execute("PRAGMA foreign_keys = ON")
        report = csv_import.run_import(conn, args.directory, apply=args.apply, postgres=postgres)
        if report.applied and report.ok:
            conn.commit()
        else:
            conn.rollback()
    except csv_import.CsvImportError as exc:
        conn.rollback()
        print(f"Refused: {exc}")
        return 2
    except Exception as exc:  # noqa: BLE001 - database errors: roll back, report the class only
        conn.rollback()
        print(f"Import failed and was rolled back: {type(exc).__name__}: {str(exc).splitlines()[0][:200]}")
        return 1
    finally:
        conn.close()
    print(report.render())
    if args.json:
        Path(args.json).write_text(json.dumps(report.as_dict(), indent=2), encoding="utf-8")
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
