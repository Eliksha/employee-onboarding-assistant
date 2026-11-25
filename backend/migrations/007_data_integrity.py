"""Migration 007: data integrity for chat history, feedback and escalations (see backend/services/db_integrity.py).

PostgreSQL only. Idempotent: adds escalations.employee_id / escalations.message_id, foreign keys on
messages.employee_id, feedback.message_id, escalations.employee_id and escalations.message_id, CHECK
constraints (feedback rating, message found flag, escalation status), feedback.message_id NOT NULL and
supporting indexes. Refuses without changing anything while orphaned or invalid rows exist (they are
listed); never deletes or rewrites data. Fresh Docker databases get the same state from
docker/postgres/04_integrity.sql.

Modes (default is a dry run that only reads the catalog):
  --verify     read-only report (exit 1 on problems)
  (no flag)    print the plan; nothing is executed
  --apply      execute the plan in ONE transaction, verify, then commit

Connection: as the table owner (PG_ADMIN_USER / PG_ADMIN_PASSWORD, falling back to PG_USER / PG_PASSWORD).
Docker:  docker compose --env-file <secrets file> run --rm --no-deps -e PG_ADMIN_USER=onboardai -e PG_ADMIN_PASSWORD \
             backend python backend/migrations/007_data_integrity.py --apply      (runbook section 11)
"""
import argparse
import importlib.util
import json
import sys
from pathlib import Path

if __name__ == "__main__":  # allow `python backend/migrations/007_...py` without PYTHONPATH
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.config import settings
from backend.services import db_integrity, db_roles


def _admin_connection():
    spec = importlib.util.spec_from_file_location(
        "migration_005", Path(__file__).with_name("005_least_privilege_roles.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.admin_connection()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="execute the plan (one transaction)")
    mode.add_argument("--verify", action="store_true", help="read-only verification report")
    args = parser.parse_args(argv)

    if settings.db_backend.strip().lower() != "postgresql":
        print("Migration 007 applies to PostgreSQL only (SQLite gets the columns at startup); nothing to do.")
        return 0

    conn = _admin_connection()
    try:
        if args.verify:
            conn.set_session(readonly=True)
            report = db_integrity.verify(conn)
            conn.rollback()
            print(json.dumps(report, indent=2))
            return 1 if report["problems"] else 0

        plan = db_integrity.build_plan(conn)
        rendered = plan.render(conn)
        if not args.apply:
            conn.rollback()
            print("-- DRY RUN: nothing executed. Re-run with --apply to execute.\n")
            print("\n\n".join(rendered) if rendered else "-- nothing to do: the integrity constraints are in place")
            return 0

        db_roles.apply_plan(conn, plan)
        report = db_integrity.verify(conn)
        if report["problems"]:
            conn.rollback()
            print("Verification failed; transaction rolled back:\n" + "\n".join(report["problems"]))
            return 1
        conn.commit()
        print(f"Migration 007 applied: {len(plan.steps)} statements; integrity constraints verified.")
        return 0
    except db_roles.ProvisioningError as exc:
        conn.rollback()
        print(f"Refused: {exc}")
        return 2
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
