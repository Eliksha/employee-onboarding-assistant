"""Migration 006: dedicated least-privilege CSV import role (`onboardai_importer`).

PostgreSQL only. Idempotent and additive: creates the role if missing, resets the grants of THIS role
only (INSERT/UPDATE on reference tables, INSERT-only on checklist_assignments, no DELETE/TRUNCATE/DDL,
no access to auth, chat, feedback, escalation or ticket tables or to the signing-key schemas) and adds
an import policy on the row-level-security tables it writes. The application and reader roles from
migration 005 are not changed. Requires migration 005 (roles, RLS) to have been applied.

Modes (default is a dry run that only reads the catalog):
  --verify     read-only report (exit 1 on problems)
  (no flag)    print the plan, password redacted; nothing is executed
  --apply      execute the plan in ONE transaction, verify, then commit

Connection: as the table owner / an administrator (PG_ADMIN_USER / PG_ADMIN_PASSWORD, falling back to
PG_USER / PG_PASSWORD); PG_HOST / PG_PORT / PG_DATABASE from settings.
New role password (environment only, at least 16 characters): ONBOARDAI_IMPORT_DB_PASSWORD

Docker:  docker compose --env-file <secrets file> run --rm --no-deps -e ONBOARDAI_IMPORT_DB_PASSWORD \
             -e PG_ADMIN_USER=onboardai -e PG_ADMIN_PASSWORD backend python backend/migrations/006_import_role.py --apply
         (full steps: docs/runbook.md section 10)
"""
import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

if __name__ == "__main__":  # allow `python backend/migrations/006_...py` without PYTHONPATH
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.config import settings
from backend.services import db_roles


def _admin_connection():
    spec = importlib.util.spec_from_file_location(
        "migration_005", Path(__file__).with_name("005_least_privilege_roles.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    conn = module.admin_connection()
    conn.set_client_encoding("UTF8")
    return conn


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="execute the plan (one transaction)")
    mode.add_argument("--verify", action="store_true", help="read-only verification report")
    parser.add_argument("--reset-password", action="store_true", help="set a new password on the existing role")
    parser.add_argument("--import-role", default=db_roles.IMPORT_ROLE)
    args = parser.parse_args(argv)

    if settings.db_backend.strip().lower() != "postgresql":
        print("Migration 006 applies to PostgreSQL only (DB_BACKEND is not postgresql); nothing to do.")
        return 0

    conn = _admin_connection()
    try:
        if args.verify:
            conn.set_session(readonly=True)
            report = db_roles.verify_import_role(conn, args.import_role)
            conn.rollback()
            print(json.dumps(report, indent=2, default=str))
            return 1 if report["problems"] else 0

        plan = db_roles.build_import_plan(conn, import_role=args.import_role,
                                          password=os.environ.get("ONBOARDAI_IMPORT_DB_PASSWORD") or None,
                                          reset_password=args.reset_password)
        rendered = plan.render(conn)
        if not args.apply:
            conn.rollback()
            print("-- DRY RUN: nothing executed. Re-run with --apply to execute.\n")
            print("\n\n".join(rendered))
            for note in plan.notes:
                print(f"\nNOTE: {note}")
            return 0

        db_roles.apply_plan(conn, plan)
        report = db_roles.verify_import_role(conn, args.import_role)
        if report["problems"]:
            conn.rollback()
            print("Verification failed; transaction rolled back:\n" + "\n".join(report["problems"]))
            return 1
        conn.commit()
        print(f"Migration 006 applied: {len(plan.steps)} statements, role {args.import_role} verified.")
        for note in plan.notes:
            print(f"NOTE: {note}")
        return 0
    except db_roles.ProvisioningError as exc:
        conn.rollback()
        print(f"Refused: {exc}")
        return 2
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
