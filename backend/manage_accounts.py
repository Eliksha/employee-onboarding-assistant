"""Development-only account provisioning for OnboardAI.

Passwords are never accepted as command-line arguments (they would leak into shell history and
process lists). They are read from a hidden prompt, or from an environment variable you name.

Examples (project root, or inside the backend container):
  python -m backend.manage_accounts list
  python -m backend.manage_accounts set --email aarav.sharma@example.com --employee-id EMP001
  python -m backend.manage_accounts set --email admin@novatech.example --role admin --password-env ONBOARDAI_NEW_PASSWORD
  python -m backend.manage_accounts disable --email aarav.sharma@example.com

`set` is idempotent: it creates the account or updates its password/role/employee link and
signs out all of the account's existing sessions. Refuses to run when APP_ENV=production.
"""
import argparse
import getpass
import os
import sys

from backend.config import settings
from backend.services import auth


def _read_password(env_name: str | None) -> str:
    if env_name:
        value = os.environ.get(env_name, "")
        if not value:
            raise SystemExit(f"Environment variable {env_name} is empty or not set.")
        return value
    if not sys.stdin.isatty():
        raise SystemExit("No terminal for a hidden prompt; use --password-env NAME instead.")
    first = getpass.getpass("New password: ")
    if first != getpass.getpass("Repeat password: "):
        raise SystemExit("Passwords do not match.")
    return first


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Development-only OnboardAI account provisioning.")
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("set", help="create or update an account")
    s.add_argument("--email", required=True)
    s.add_argument("--employee-id", default=None, help="required for role 'employee'")
    s.add_argument("--role", choices=auth.ROLES, default="employee")
    s.add_argument("--password-env", default=None, help="read the password from this environment variable")
    d = sub.add_parser("disable", help="deactivate an account and end its sessions")
    d.add_argument("--email", required=True)
    sub.add_parser("list", help="list accounts (no secrets)")
    args = parser.parse_args(argv)

    if settings.app_env.strip().lower() == "production":
        raise SystemExit("Refusing to run: APP_ENV=production. This tool is for development only.")

    if args.command == "list":
        for a in auth.list_accounts():
            state = "active" if a["is_active"] else "disabled"
            print(f"{a['email']:<36} role={a['role']:<9} employee_id={a['employee_id'] or '-':<8} {state}")
        return 0
    if args.command == "disable":
        print("Account disabled." if auth.set_account_active(args.email, False) else "No such account.")
        return 0
    try:
        auth.upsert_account(args.email, _read_password(args.password_env), args.employee_id, args.role)
    except auth.AccountError as exc:
        raise SystemExit(f"Error: {exc}")
    print(f"Account ready: {auth.normalize_email(args.email)} (role={args.role}, employee_id={args.employee_id or '-'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
