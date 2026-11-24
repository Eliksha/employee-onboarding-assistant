"""Migration 008: HR/IT escalation queue, escalation audit trail and shared login rate limiting.

PostgreSQL only. Idempotent and additive (see backend/services/hr_queue_schema.py): adds the `hr` role to the
user_accounts CHECK constraints, three nullable columns on escalations (updated_at, resolution_note,
handled_by), the escalation_events audit table and the login_failures table, then grants the application role
exactly the privileges of backend/services/db_roles.APP_PRIVILEGES on these objects. Never deletes or rewrites
data. Fresh Docker databases get the same objects from docker/postgres/05_hr_queue.sql (grants come from 005).

Order on an existing database: back up (runbook section 12) -> 008 --apply -> 008 --verify. Migration 005
--apply afterwards is optional (it re-grants the same privileges).

Modes (default is a dry run that only reads the catalog):
  --verify     read-only report (exit 1 on problems)
  (no flag)    print the plan; nothing is executed
  --apply      execute DDL + grants in ONE transaction, verify, then commit

Connection: as the table owner (PG_ADMIN_USER / PG_ADMIN_PASSWORD, falling back to PG_USER / PG_PASSWORD).
Docker:  docker compose --env-file <secrets file> run --rm --no-deps -e PG_ADMIN_USER=onboardai -e PG_ADMIN_PASSWORD \
             backend python backend/migrations/008_hr_escalation_queue.py --apply      (runbook section 14)
"""
import argparse
import importlib.util
import json
import sys
from pathlib import Path

if __name__ == "__main__":  # allow `python backend/migrations/008_...py` without PYTHONPATH
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.config import settings
from backend.services import db_roles, hr_queue_schema


def _admin_connection():
    spec = importlib.util.spec_from_file_location(
        "migration_005", Path(__file__).with_name("005_least_privilege_roles.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.admin_connection()


def report(conn, app_role: str) -> dict:
    missing = hr_queue_schema.missing_objects(conn)
    problems = [f"missing: {m}" for m in missing]
    if not missing:
        problems += hr_queue_schema.privilege_problems(conn, app_role)
    return {"missing_objects": missing, "problems": problems}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="execute DDL + grants (one transaction)")
    mode.add_argument("--verify", action="store_true", help="read-only verification report")
    parser.add_argument("--app-role", default=db_roles.APP_ROLE)
    args = parser.parse_args(argv)

    if settings.db_backend.strip().lower() != "postgresql":
        print("Migration 008 applies to PostgreSQL only (SQLite gets the tables at startup); nothing to do.")
        return 0

    conn = _admin_connection()
    try:
        if args.verify:
            conn.set_session(readonly=True)
            result = report(conn, args.app_role)
            conn.rollback()
            print(json.dumps(result, indent=2))
            return 1 if result["problems"] else 0

        ddl = hr_queue_schema.build_ddl_plan()
        if not args.apply:
            rendered = ddl.render(conn)
            conn.rollback()
            print("-- DRY RUN: nothing executed. Re-run with --apply to execute.\n")
            print(";\n\n".join(rendered) + ";")
            print(f"\n-- then: grants for role {args.app_role} on escalations, escalation_events, login_failures "
                  "(db_roles.APP_PRIVILEGES), computed after the DDL")
            return 0

        db_roles.apply_plan(conn, ddl)
        grants = hr_queue_schema.build_grant_plan(conn, args.app_role)
        db_roles.apply_plan(conn, grants)
        result = report(conn, args.app_role)
        if result["problems"]:
            conn.rollback()
            print("Verification failed; transaction rolled back:\n" + "\n".join(result["problems"]))
            return 1
        conn.commit()
        for note in grants.notes:
            print("Note: " + note)
        print(f"Migration 008 applied: {len(ddl.steps)} DDL statements, {len(grants.steps)} grants; verified.")
        return 0
    except db_roles.ProvisioningError as exc:
        conn.rollback()
        print(f"Refused: {exc}")
        return 2
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
