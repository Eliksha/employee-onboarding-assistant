"""Least-privilege PostgreSQL roles for OnboardAI (single source of truth for grants).

Roles
-----
* APP role (default `onboardai_app`): what the FastAPI application needs and nothing more - SELECT
  on reference data, INSERT for chat history, feedback, escalations, tickets and accounts, UPDATE on
  specific columns only, DELETE only on user_sessions. No DDL, no TRUNCATE, not a superuser, cannot
  create roles or databases, does not bypass row-level security.
* READER role (default `onboardai_reader`): SQL-agent / read-only access. SELECT on employee-facing
  data tables only (no auth, chat history, feedback or escalation tables), read-only transactions
  by default, a role-level statement timeout, and row-level security that shows only the rows of
  the employee in a SIGNED scope: the policy calls `onboardai_rls.current_employee()`, a SECURITY
  DEFINER function that verifies an HMAC over (employee, connection id, expiry) with a key kept in
  `onboardai_private.scope_key`. Neither role can read that schema, so changing `app.*` session
  settings (SET, set_config) cannot widen the scope, and a signature cannot be replayed from another
  connection (see backend/services/employee_scope.py).

Schema changes (migrations) keep running as the database owner, never as these roles.

Provisioning is idempotent and additive: roles are created if missing (passwords are sent to the
server already SCRAM-hashed), grants are reset for these two roles only, the scope key is stored
once (rotated only on request), the verification functions are (re)created, RLS policies are created
or updated. Nothing is dropped and no application data is changed. See backend/migrations/005_least_privilege_roles.py.
"""
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import psycopg2
from psycopg2 import sql
from psycopg2.extensions import encrypt_password

from backend.services import employee_scope

APP_ROLE = "onboardai_app"
READER_ROLE = "onboardai_reader"
PRIVATE_SCHEMA = "onboardai_private"   # signing key; no access for the app or reader roles
RLS_SCHEMA = "onboardai_rls"           # verification functions; USAGE + EXECUTE for the reader only

# (privilege, columns or None). Derived from every SQL statement in backend/services (auth.py, db.py,
# employee_db.py). Adding a table or statement requires updating this map (tests enforce coverage).
APP_PRIVILEGES: Dict[str, Tuple[Tuple[str, Optional[Tuple[str, ...]]], ...]] = {
    "employees": (("SELECT", None),),
    "leave_balances": (("SELECT", None),),
    "assets": (("SELECT", None),),
    "payroll_calendar": (("SELECT", None),),
    "checklist": (("SELECT", None), ("UPDATE", ("done",))),                 # legacy admin checklist
    "checklist_assignments": (("SELECT", None), ("UPDATE", ("done",))),
    "tickets": (("SELECT", None), ("INSERT", None)),
    "messages": (("SELECT", None), ("INSERT", None)),
    "feedback": (("SELECT", None), ("INSERT", None)),
    "escalations": (("SELECT", None), ("INSERT", None)),                    # SELECT for RETURNING id
    "user_accounts": (("SELECT", None), ("INSERT", None),
                      ("UPDATE", ("password_hash", "employee_id", "role", "is_active", "updated_at"))),
    "user_sessions": (("SELECT", None), ("INSERT", None), ("UPDATE", ("last_seen_at",)), ("DELETE", None)),
}

# Identity columns the APP role inserts into (sequence USAGE is granted for these only).
APP_IDENTITY_COLUMNS: Dict[str, str] = {
    "tickets": "ticket_id",
    "messages": "id",
    "feedback": "id",
    "escalations": "id",
    "user_accounts": "id",
}

# SQL-agent visible tables. Auth, chat history, feedback and escalations are deliberately excluded.
READER_TABLES: Tuple[str, ...] = (
    "employees", "leave_balances", "assets", "payroll_calendar", "checklist", "checklist_assignments", "tickets",
)

# Tables with an employee_id column: the READER role sees only the scoped employee's rows.
RLS_TABLES: Tuple[str, ...] = ("employees", "leave_balances", "assets", "checklist_assignments", "tickets")

APP_ROLE_SETTINGS = {"statement_timeout": "15s", "idle_in_transaction_session_timeout": "60s"}
READER_ROLE_SETTINGS = {
    "default_transaction_read_only": "on",
    "statement_timeout": "5s",
    "idle_in_transaction_session_timeout": "10s",
}
APP_CONNECTION_LIMIT = 20
READER_CONNECTION_LIMIT = 10
MIN_PASSWORD_LENGTH = 16

ROLE_NAME_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
ROLE_ATTRIBUTES = "LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS"


class ProvisioningError(RuntimeError):
    """Provisioning refused (unsafe role name, missing password, insufficient privileges...)."""


@dataclass
class Step:
    description: str
    statement: sql.Composable
    params: Tuple = ()
    secret: bool = False  # params contain a (hashed) password: never rendered


@dataclass
class Plan:
    steps: List[Step] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def add(self, description, statement, params=(), secret=False):
        self.steps.append(Step(description, statement, tuple(params), secret))

    def render(self, conn) -> List[str]:
        """Human-readable SQL with passwords redacted (safe to print or log)."""
        out = []
        for step in self.steps:
            text = step.statement.as_string(conn)
            if step.secret:
                text = text.replace("%s", "'<redacted SCRAM-SHA-256 hash>'")
            elif step.params:
                text = conn.cursor().mogrify(text, step.params).decode()
            out.append(f"-- {step.description}\n{text};")
        return out


def _ident(name: str) -> sql.Identifier:
    return sql.Identifier(name)


def _table(name: str) -> sql.Composed:
    return sql.SQL("{}.{}").format(sql.Identifier("public"), sql.Identifier(name))


def validate_role_names(app_role: str, reader_role: str) -> None:
    for name in (app_role, reader_role):
        if not ROLE_NAME_RE.match(name or ""):
            raise ProvisioningError(f"Invalid role name: {name!r}")
    if app_role == reader_role:
        raise ProvisioningError("APP and READER roles must be different")


def _one(conn, query, params=()):
    with conn.cursor() as cur:
        cur.execute(query, params)
        return cur.fetchone()


def _role(conn, name: str):
    return _one(conn, """SELECT rolname, rolsuper, rolcreaterole, rolcreatedb, rolbypassrls, rolcanlogin,
        rolinherit, rolreplication, rolconnlimit FROM pg_roles WHERE rolname = %s""", (name,))


def _value(row, key, index):
    if row is None:
        return None
    return row[key] if isinstance(row, dict) else row[index]


def preflight(conn, app_role: str, reader_role: str) -> Dict[str, object]:
    """Read-only checks; raises ProvisioningError when provisioning would be unsafe or impossible."""
    validate_role_names(app_role, reader_role)
    me = _one(conn, "SELECT current_user, current_database()")
    current_user, database = _value(me, "current_user", 0), _value(me, "current_database", 1)
    if current_user in (app_role, reader_role):
        raise ProvisioningError("Run provisioning as the database owner/administrator, not as a target role")
    owners = {}
    with conn.cursor() as cur:
        cur.execute("""SELECT c.relname, pg_get_userbyid(c.relowner) FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relname = ANY(%s)""",
                    (list(APP_PRIVILEGES),))
        for row in cur.fetchall():
            name = _value(row, "relname", 0)
            owner = row["pg_get_userbyid"] if isinstance(row, dict) else row[1]
            owners[name] = owner
    missing = sorted(set(APP_PRIVILEGES) - set(owners))
    if missing:
        raise ProvisioningError(f"Tables missing in schema public: {', '.join(missing)} (run migrations first)")
    for name in (app_role, reader_role):
        row = _role(conn, name)
        if row is not None and (_value(row, "rolsuper", 1) or name in owners.values()):
            raise ProvisioningError(
                f"Role {name} already exists and is a superuser or owns application tables; refusing to "
                "change it. Choose a different role name."
            )
    me_role = _role(conn, current_user)
    if not (_value(me_role, "rolsuper", 1) or _value(me_role, "rolcreaterole", 2)):
        raise ProvisioningError(f"{current_user} cannot create roles (needs SUPERUSER or CREATEROLE)")
    if not _value(me_role, "rolsuper", 1) and set(owners.values()) != {current_user}:
        raise ProvisioningError(f"{current_user} must own the application tables (or be a superuser)")
    stats = _one(conn, "SELECT pg_has_role(current_user, 'pg_read_all_stats', 'USAGE') AS ok")
    if not (_value(me_role, "rolsuper", 1) or _value(stats, "ok", 0)):
        raise ProvisioningError(f"{current_user} must be a superuser or a member of pg_read_all_stats "
                                "(the scope verifier reads pg_stat_activity.backend_start)")
    return {"current_user": current_user, "database": database, "table_owners": owners}


def _stored_pads(conn):
    exists = _one(conn, "SELECT to_regclass('onboardai_private.scope_key') IS NOT NULL AS ok")
    if not _value(exists, "ok", 0):
        return None
    row = _one(conn, "SELECT k_ipad, k_opad FROM onboardai_private.scope_key WHERE id = 1")
    if row is None:
        return None
    return bytes(_value(row, "k_ipad", 0)), bytes(_value(row, "k_opad", 1))


def build_plan(
    conn,
    *,
    app_role: str = APP_ROLE,
    reader_role: str = READER_ROLE,
    app_password: Optional[str] = None,
    reader_password: Optional[str] = None,
    reset_passwords: bool = False,
    scope_secret: Optional[str] = None,
    rotate_scope_secret: bool = False,
) -> Plan:
    """Compute the idempotent provisioning plan (reads the catalog only)."""
    info = preflight(conn, app_role, reader_role)
    database = info["database"]
    plan = Plan()

    for role, password, limit in ((app_role, app_password, APP_CONNECTION_LIMIT),
                                  (reader_role, reader_password, READER_CONNECTION_LIMIT)):
        exists = _role(conn, role) is not None
        attributes = sql.SQL(ROLE_ATTRIBUTES + " CONNECTION LIMIT {}").format(sql.Literal(limit))
        if not exists:
            if not password:
                raise ProvisioningError(f"A password is required to create role {role}")
            if len(password) < MIN_PASSWORD_LENGTH:
                raise ProvisioningError(f"Password for {role} must be at least {MIN_PASSWORD_LENGTH} characters")
            hashed = encrypt_password(password, role, scope=conn)
            plan.add(f"create login role {role}",
                     sql.SQL("CREATE ROLE {} WITH {} PASSWORD %s").format(_ident(role), attributes),
                     (hashed,), secret=True)
        else:
            plan.add(f"enforce least-privilege attributes on existing role {role}",
                     sql.SQL("ALTER ROLE {} WITH {}").format(_ident(role), attributes))
            if reset_passwords:
                if not password or len(password) < MIN_PASSWORD_LENGTH:
                    raise ProvisioningError(f"--reset-passwords needs a password of at least "
                                            f"{MIN_PASSWORD_LENGTH} characters for {role}")
                hashed = encrypt_password(password, role, scope=conn)
                plan.add(f"set new password for {role}",
                         sql.SQL("ALTER ROLE {} WITH PASSWORD %s").format(_ident(role)), (hashed,), secret=True)
            elif password:
                plan.notes.append(f"Role {role} already exists: its password was NOT changed "
                                  "(use --reset-passwords to rotate it).")

    for role, settings_map in ((app_role, APP_ROLE_SETTINGS), (reader_role, READER_ROLE_SETTINGS)):
        for name, value in settings_map.items():
            plan.add(f"{role}: {name} = {value} (this database only)",
                     sql.SQL("ALTER ROLE {} IN DATABASE {} SET {} = {}").format(
                         _ident(role), _ident(database), sql.Identifier(name), sql.Literal(value)))

    plan.add("no temporary tables for roles that inherit PUBLIC privileges",
             sql.SQL("REVOKE TEMPORARY ON DATABASE {} FROM PUBLIC").format(_ident(database)))
    plan.add("nobody but the owner may create objects in schema public",
             sql.SQL("REVOKE CREATE ON SCHEMA public FROM PUBLIC"))
    plan.add("connect + schema usage for both roles",
             sql.SQL("GRANT CONNECT ON DATABASE {} TO {}, {}").format(
                 _ident(database), _ident(app_role), _ident(reader_role)))
    plan.add("schema usage",
             sql.SQL("GRANT USAGE ON SCHEMA public TO {}, {}").format(_ident(app_role), _ident(reader_role)))
    plan.add("reset table privileges of the two roles (clean, repeatable state)",
             sql.SQL("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {}, {}").format(
                 _ident(app_role), _ident(reader_role)))
    plan.add("reset sequence privileges of the two roles",
             sql.SQL("REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {}, {}").format(
                 _ident(app_role), _ident(reader_role)))

    for table, privileges in APP_PRIVILEGES.items():
        for privilege, columns in privileges:
            target = (sql.SQL("{} ({})").format(sql.SQL(privilege), sql.SQL(", ").join(map(_ident, columns)))
                      if columns else sql.SQL(privilege))
            plan.add(f"{app_role}: {privilege}{'(' + ', '.join(columns) + ')' if columns else ''} on {table}",
                     sql.SQL("GRANT {} ON {} TO {}").format(target, _table(table), _ident(app_role)))

    for table, column in APP_IDENTITY_COLUMNS.items():
        seq = _one(conn, "SELECT pg_get_serial_sequence(%s, %s)", (f"public.{table}", column))
        seq_name = _value(seq, "pg_get_serial_sequence", 0)
        if seq_name:
            plan.add(f"{app_role}: identity sequence for {table}.{column}",
                     sql.SQL("GRANT USAGE ON SEQUENCE {} TO {}").format(sql.SQL(seq_name), _ident(app_role)))

    for table in READER_TABLES:
        plan.add(f"{reader_role}: SELECT on {table}",
                 sql.SQL("GRANT SELECT ON {} TO {}").format(_table(table), _ident(reader_role)))

    _plan_scope_verifier(plan, conn, reader_role, app_role, scope_secret, rotate_scope_secret)

    for table in RLS_TABLES:
        plan.add(f"row-level security on {table} (table owner and superusers are unaffected)",
                 sql.SQL("ALTER TABLE {} ENABLE ROW LEVEL SECURITY").format(_table(table)))
        app_policy = f"{app_role}_all"
        if not _policy_exists(conn, table, app_policy):
            plan.add(f"policy {app_policy} on {table}",
                     sql.SQL("CREATE POLICY {} ON {} AS PERMISSIVE FOR ALL TO {} USING (true) WITH CHECK (true)")
                     .format(_ident(app_policy), _table(table), _ident(app_role)))
        reader_policy = f"{reader_role}_own_employee"
        expression = sql.SQL(employee_scope.READER_POLICY_EXPRESSION)
        if _policy_exists(conn, table, reader_policy):
            plan.add(f"policy {reader_policy} on {table}: signed employee scope",
                     sql.SQL("ALTER POLICY {} ON {} TO {} USING ({})").format(
                         _ident(reader_policy), _table(table), _ident(reader_role), expression))
        else:
            plan.add(f"policy {reader_policy} on {table}: signed employee scope",
                     sql.SQL("CREATE POLICY {} ON {} AS PERMISSIVE FOR SELECT TO {} USING ({})").format(
                         _ident(reader_policy), _table(table), _ident(reader_role), expression))
    return plan


def _policy_exists(conn, table: str, name: str) -> bool:
    return _one(conn, "SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = %s "
                      "AND policyname = %s", (table, name)) is not None


def _plan_scope_verifier(plan: Plan, conn, reader_role: str, app_role: str,
                         scope_secret: Optional[str], rotate: bool) -> None:
    """Private signing key + SECURITY DEFINER verifier used by the reader's RLS policies."""
    private, rls = _ident(PRIVATE_SCHEMA), _ident(RLS_SCHEMA)
    roles = sql.SQL("PUBLIC, {}, {}").format(_ident(app_role), _ident(reader_role))
    plan.add("private schema for the scope signing key (owner only)",
             sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(private))
    plan.add("no access to the private schema for anyone but the owner",
             sql.SQL("REVOKE ALL ON SCHEMA {} FROM {}").format(private, roles))
    plan.add("scope signing key table (HMAC-SHA256 inner/outer padded keys)",
             sql.SQL("CREATE TABLE IF NOT EXISTS {}.scope_key (id integer PRIMARY KEY CHECK (id = 1), "
                     "k_ipad bytea NOT NULL, k_opad bytea NOT NULL, "
                     "created_at timestamptz NOT NULL DEFAULT now())").format(private))
    plan.add("no access to the signing key table for anyone but the owner",
             sql.SQL("REVOKE ALL ON TABLE {}.scope_key FROM {}").format(private, roles))

    stored = _stored_pads(conn)
    if scope_secret is not None:
        try:
            pads = employee_scope.hmac_pads(scope_secret)
        except employee_scope.ScopeError as exc:
            raise ProvisioningError(str(exc)) from exc
    else:
        pads = None
    if stored is None:
        if pads is None:
            raise ProvisioningError("ONBOARDAI_SCOPE_SECRET (32+ characters) is required to create the scope key")
        plan.add("store the scope signing key",
                 sql.SQL("INSERT INTO {}.scope_key (id, k_ipad, k_opad) VALUES (1, %s, %s)").format(private),
                 (psycopg2.Binary(pads[0]), psycopg2.Binary(pads[1])), secret=True)
    elif rotate:
        if pads is None:
            raise ProvisioningError("--rotate-scope-secret needs ONBOARDAI_SCOPE_SECRET")
        plan.add("rotate the scope signing key (backend PG_SCOPE_SECRET must change at the same time)",
                 sql.SQL("UPDATE {}.scope_key SET k_ipad = %s, k_opad = %s, created_at = now() WHERE id = 1")
                 .format(private), (psycopg2.Binary(pads[0]), psycopg2.Binary(pads[1])), secret=True)
    elif pads is not None and pads != stored:
        plan.notes.append("The stored scope key does NOT match ONBOARDAI_SCOPE_SECRET; it was not changed. "
                          "Use the original secret for PG_SCOPE_SECRET or re-run with --rotate-scope-secret.")
    elif pads is not None:
        plan.notes.append("The stored scope key matches ONBOARDAI_SCOPE_SECRET.")

    plan.add("schema for the scope verification functions",
             sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(rls))
    plan.add("verification schema: no default access",
             sql.SQL("REVOKE ALL ON SCHEMA {} FROM {}").format(rls, roles))
    plan.add("verification schema: usage for the reader role only",
             sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(rls, _ident(reader_role)))
    plan.add("connection id helper (pid + backend start)", sql.SQL(employee_scope.CONNECTION_ID_SQL.strip()))
    plan.add("SECURITY DEFINER scope verifier (HMAC, connection-bound, expiring)",
             sql.SQL(employee_scope.CURRENT_EMPLOYEE_SQL.strip()))
    functions = sql.SQL("{rls}.connection_id(), {rls}.current_employee()").format(rls=rls)
    plan.add("verification functions: no default EXECUTE",
             sql.SQL("REVOKE ALL ON FUNCTION {} FROM {}").format(functions, roles))
    plan.add("verification functions: EXECUTE for the reader role only",
             sql.SQL("GRANT EXECUTE ON FUNCTION {} TO {}").format(functions, _ident(reader_role)))


def apply_plan(conn, plan: Plan) -> None:
    """Execute the plan in the caller's transaction (the caller commits or rolls back)."""
    with conn.cursor() as cur:
        for step in plan.steps:
            cur.execute(step.statement, step.params or None)


def verify(conn, app_role: str = APP_ROLE, reader_role: str = READER_ROLE,
           scope_secret: Optional[str] = None) -> Dict[str, object]:
    """Read-only report of role attributes, effective privileges, RLS and signed-scope state."""
    report: Dict[str, object] = {"roles": {}, "privileges": {}, "rls": {}, "scope": {}, "problems": []}
    problems: List[str] = report["problems"]  # type: ignore[assignment]
    for role in (app_role, reader_role):
        row = _role(conn, role)
        if row is None:
            problems.append(f"role {role} does not exist")
            continue
        attrs = dict(row) if isinstance(row, dict) else dict(zip(
            ("rolname", "rolsuper", "rolcreaterole", "rolcreatedb", "rolbypassrls", "rolcanlogin",
             "rolinherit", "rolreplication", "rolconnlimit"), row))
        report["roles"][role] = attrs
        for flag in ("rolsuper", "rolcreaterole", "rolcreatedb", "rolbypassrls", "rolreplication"):
            if attrs[flag]:
                problems.append(f"{role} has {flag}")
    if problems:
        return report

    def has(role, table, privilege):
        return bool(_value(_one(conn, "SELECT has_table_privilege(%s, %s, %s) AS ok",
                                (role, f"public.{table}", privilege)), "ok", 0))

    all_tables = sorted(set(APP_PRIVILEGES) | set(READER_TABLES))
    for role in (app_role, reader_role):
        report["privileges"][role] = {
            t: [p for p in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")
                if has(role, t, p)] for t in all_tables
        }
    for table in all_tables:
        reader_privs = report["privileges"][reader_role][table]
        if table in READER_TABLES and reader_privs != ["SELECT"]:
            problems.append(f"{reader_role} on {table}: expected SELECT only, has {reader_privs}")
        if table not in READER_TABLES and reader_privs:
            problems.append(f"{reader_role} must not access {table}, has {reader_privs}")
        app_privs = report["privileges"][app_role][table]
        if "TRUNCATE" in app_privs or ("DELETE" in app_privs and table != "user_sessions"):
            problems.append(f"{app_role} has destructive privileges on {table}: {app_privs}")
    for table in RLS_TABLES:
        enabled = _value(_one(conn, """SELECT c.relrowsecurity FROM pg_class c JOIN pg_namespace n
            ON n.oid = c.relnamespace WHERE n.nspname = 'public' AND c.relname = %s""", (table,)),
                         "relrowsecurity", 0)
        report["rls"][table] = bool(enabled)
        if not enabled:
            problems.append(f"row-level security is not enabled on {table}")
        qual = _value(_one(conn, "SELECT qual FROM pg_policies WHERE schemaname = 'public' AND tablename = %s "
                                 "AND policyname = %s", (table, f"{reader_role}_own_employee")), "qual", 0)
        if not qual or "onboardai_rls.current_employee()" not in qual:
            problems.append(f"reader policy on {table} does not use the signed scope verifier: {qual}")
    _verify_scope(conn, app_role, reader_role, scope_secret, report["scope"], problems)
    return report


def _verify_scope(conn, app_role, reader_role, scope_secret, scope, problems) -> None:
    stored = _stored_pads(conn)
    scope["key_present"] = stored is not None
    if stored is None:
        problems.append("scope signing key is missing (onboardai_private.scope_key)")
        return
    if scope_secret:
        scope["key_matches_secret"] = employee_scope.hmac_pads(scope_secret) == stored
        if not scope["key_matches_secret"]:
            problems.append("stored scope key does not match the provided scope secret")
    for role in (app_role, reader_role, "public"):
        usage = _value(_one(conn, "SELECT has_schema_privilege(%s, %s, 'USAGE') AS ok",
                            (role, PRIVATE_SCHEMA)), "ok", 0)
        key = _value(_one(conn, "SELECT has_table_privilege(%s, 'onboardai_private.scope_key', 'SELECT') AS ok",
                          (role,)), "ok", 0)
        scope[f"{role}_can_reach_key"] = bool(usage or key)
        if usage or key:
            problems.append(f"{role} can reach the scope signing key (schema usage={usage}, select={key})")
    fn = _one(conn, """SELECT p.prosecdef, p.proconfig, pg_get_userbyid(p.proowner) AS owner
        FROM pg_proc p WHERE p.oid = to_regprocedure('onboardai_rls.current_employee()')""")
    if fn is None:
        problems.append("onboardai_rls.current_employee() is missing")
        return
    config = list(_value(fn, "proconfig", 1) or [])
    scope["verifier_security_definer"] = bool(_value(fn, "prosecdef", 0))
    scope["verifier_search_path_pinned"] = "search_path=pg_catalog, pg_temp" in config
    if not (scope["verifier_security_definer"] and scope["verifier_search_path_pinned"]):
        problems.append(f"scope verifier must be SECURITY DEFINER with a pinned search_path: {config}")
    for role, expected in ((reader_role, True), (app_role, False), ("public", False)):
        ok = bool(_value(_one(conn, "SELECT has_function_privilege(%s, 'onboardai_rls.current_employee()', "
                                    "'EXECUTE') AS ok", (role,)), "ok", 0))
        scope[f"{role}_can_execute_verifier"] = ok
        if ok != expected:
            problems.append(f"{role} EXECUTE on the scope verifier is {ok}, expected {expected}")
