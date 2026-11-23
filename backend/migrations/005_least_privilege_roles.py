"""Migration 005: least-privilege PostgreSQL roles (APP + READER) and signed row-level security.

PostgreSQL only. Idempotent and additive: creates the roles if missing, resets the grants of these two
roles only, stores the employee-scope signing key in the owner-only schema onboardai_private (once;
rotated only with --rotate-scope-secret), (re)creates the SECURITY DEFINER scope verifier in
onboardai_rls, enables row-level security on employee tables and creates/updates the policies. Never
drops anything, never changes application data, never changes the password of an existing role
unless --reset-passwords is given. The owner/superuser keeps bypassing row-level security, so an
application still connected as the owner keeps working unchanged.

Modes (default is a dry run that only reads the catalog):
  --verify     read-only report of roles, privileges and RLS state (exit 1 on problems)
  (no flag)    print the plan, passwords redacted; nothing is executed
  --apply      execute the plan in ONE transaction (all-or-nothing), then verify

Connection: runs as an administrator that owns the tables (or a superuser):
  PG_ADMIN_USER / PG_ADMIN_PASSWORD (environment), falling back to PG_USER / PG_PASSWORD.
  PG_HOST / PG_PORT / PG_DATABASE come from the normal settings.
New role passwords (environment only, never arguments; at least 16 characters):
  ONBOARDAI_APP_DB_PASSWORD, ONBOARDAI_READER_DB_PASSWORD
Employee-scope HMAC secret (environment only, at least 32 characters; the backend needs the SAME
value as PG_SCOPE_SECRET): ONBOARDAI_SCOPE_SECRET (falls back to PG_SCOPE_SECRET)

Usage (project root):  $env:PYTHONPATH = "."; python backend/migrations/005_least_privilege_roles.py --verify
Docker:  docker compose run --rm --no-deps -e ONBOARDAI_APP_DB_PASSWORD -e ONBOARDAI_READER_DB_PASSWORD \
             -e ONBOARDAI_SCOPE_SECRET backend python backend/migrations/005_least_privilege_roles.py --apply
         (full steps: docs/runbook.md section 9)
"""
import argparse
import json
import os
import sys
from pathlib import Path

if __name__ == "__main__":  # allow `python backend/migrations/005_...py` without PYTHONPATH
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import psycopg2
from psycopg2.extras import RealDictCursor

from backend.config import settings
from backend.services import db_roles


def admin_connection():
    return psycopg2.connect(
        host=settings.pg_host,
        port=settings.pg_port,
        dbname=settings.pg_database,
        user=os.environ.get("PG_ADMIN_USER") or settings.pg_user,
        password=os.environ.get("PG_ADMIN_PASSWORD") or settings.pg_password or os.environ.get("PGPASSWORD", ""),
        connect_timeout=10,
        cursor_factory=RealDictCursor,
        application_name="onboardai-migration-005",
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="execute the plan (one transaction)")
    mode.add_argument("--verify", action="store_true", help="read-only verification report")
    parser.add_argument("--reset-passwords", action="store_true", help="also set new passwords on existing roles")
    parser.add_argument("--rotate-scope-secret", action="store_true",
                        help="replace the stored scope signing key with ONBOARDAI_SCOPE_SECRET")
    parser.add_argument("--app-role", default=db_roles.APP_ROLE)
    parser.add_argument("--reader-role", default=db_roles.READER_ROLE)
    args = parser.parse_args(argv)

    if settings.db_backend.strip().lower() != "postgresql":
        print("Migration 005 applies to PostgreSQL only (DB_BACKEND is not postgresql); nothing to do.")
        return 0

    scope_secret = os.environ.get("ONBOARDAI_SCOPE_SECRET") or settings.pg_scope_secret or None
    conn = admin_connection()
    try:
        if args.verify:
            conn.set_session(readonly=True)
            report = db_roles.verify(conn, args.app_role, args.reader_role, scope_secret=scope_secret)
            conn.rollback()
            print(json.dumps(report, indent=2, default=str))
            return 1 if report["problems"] else 0

        plan = db_roles.build_plan(
            conn,
            app_role=args.app_role,
            reader_role=args.reader_role,
            app_password=os.environ.get("ONBOARDAI_APP_DB_PASSWORD") or None,
            reader_password=os.environ.get("ONBOARDAI_READER_DB_PASSWORD") or None,
            reset_passwords=args.reset_passwords,
            scope_secret=scope_secret,
            rotate_scope_secret=args.rotate_scope_secret,
        )
        rendered = plan.render(conn)
        if not args.apply:
            conn.rollback()
            print("-- DRY RUN: nothing executed. Re-run with --apply to execute.\n")
            print("\n\n".join(rendered))
            for note in plan.notes:
                print(f"\nNOTE: {note}")
            return 0

        db_roles.apply_plan(conn, plan)
        report = db_roles.verify(conn, args.app_role, args.reader_role, scope_secret=scope_secret)
        if report["problems"]:
            conn.rollback()
            print("Verification failed; transaction rolled back:\n" + "\n".join(report["problems"]))
            return 1
        conn.commit()
        print(f"Migration 005 applied: {len(plan.steps)} statements, roles {args.app_role} and {args.reader_role} "
              "verified.")
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
