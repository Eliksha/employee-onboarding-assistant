"""Data-integrity constraints for chat history, feedback and escalations (M5, migration 007).

Adds, idempotently and in one transaction:
  * escalations.employee_id (who escalated; NULL for accounts without an employee) and
    escalations.message_id (the chat answer that was escalated; NULL for free-text escalations)
  * foreign keys: messages.employee_id -> employees, feedback.message_id -> messages (ON DELETE CASCADE),
    escalations.employee_id -> employees, escalations.message_id -> messages (ON DELETE SET NULL)
  * feedback.message_id NOT NULL; CHECK constraints on feedback.rating, messages.found, escalations.status
  * indexes for the new foreign keys
The plan refuses (no changes) while orphaned or invalid rows exist and reports them; it never deletes or
rewrites data. `docker/postgres/04_integrity.sql` applies the same end state to fresh databases.
"""
from typing import Dict, List

from psycopg2 import sql

from backend.services.db_roles import Plan, ProvisioningError, _one, _value

ESCALATION_STATUSES = ("open", "in_progress", "resolved", "closed")

# (table, column, type) added when missing
COLUMNS = (("escalations", "employee_id", "text"), ("escalations", "message_id", "integer"))

# name -> (table, definition); added when no constraint with that name exists
CONSTRAINTS = {
    "messages_employee_id_fkey": ("messages", "FOREIGN KEY (employee_id) REFERENCES public.employees(employee_id)"),
    "messages_found_check": ("messages", "CHECK (found IN (0, 1))"),
    "feedback_message_id_fkey": ("feedback", "FOREIGN KEY (message_id) REFERENCES public.messages(id) ON DELETE CASCADE"),
    "feedback_rating_check": ("feedback", "CHECK (rating IN ('up', 'down'))"),
    "escalations_employee_id_fkey": ("escalations",
                                     "FOREIGN KEY (employee_id) REFERENCES public.employees(employee_id)"),
    "escalations_message_id_fkey": ("escalations",
                                    "FOREIGN KEY (message_id) REFERENCES public.messages(id) ON DELETE SET NULL"),
    "escalations_status_check": ("escalations",
                                 "CHECK (status IN (" + ", ".join(f"'{s}'" for s in ESCALATION_STATUSES) + "))"),
}

INDEXES = {
    "idx_feedback_message_id": ("feedback", "message_id"),
    "idx_escalations_employee_id": ("escalations", "employee_id"),
    "idx_escalations_message_id": ("escalations", "message_id"),
}

# Rows that would violate the new constraints (counted, never changed).
ORPHAN_CHECKS = {
    "messages with an unknown employee_id": """SELECT count(*) FROM public.messages m WHERE m.employee_id IS NOT NULL
        AND NOT EXISTS (SELECT 1 FROM public.employees e WHERE e.employee_id = m.employee_id)""",
    "messages with found not in (0, 1)": "SELECT count(*) FROM public.messages WHERE found IS NOT NULL AND found NOT IN (0, 1)",
    "feedback without a message": """SELECT count(*) FROM public.feedback f WHERE f.message_id IS NULL
        OR NOT EXISTS (SELECT 1 FROM public.messages m WHERE m.id = f.message_id)""",
    "feedback with a rating other than up/down": "SELECT count(*) FROM public.feedback WHERE rating IS NULL OR rating NOT IN ('up', 'down')",
    "escalations with an unknown status": "SELECT count(*) FROM public.escalations WHERE status IS NOT NULL AND status NOT IN ("
                                          + ", ".join(f"'{s}'" for s in ESCALATION_STATUSES) + ")",
}


def _column_exists(conn, table: str, column: str) -> bool:
    return _one(conn, """SELECT 1 FROM information_schema.columns WHERE table_schema = 'public'
        AND table_name = %s AND column_name = %s""", (table, column)) is not None


def _constraint_exists(conn, name: str) -> bool:
    return _one(conn, """SELECT 1 FROM pg_constraint c JOIN pg_namespace n ON n.oid = c.connamespace
        WHERE n.nspname = 'public' AND c.conname = %s""", (name,)) is not None


def _index_exists(conn, name: str) -> bool:
    return bool(_value(_one(conn, "SELECT to_regclass(%s) IS NOT NULL AS ok", (f"public.{name}",)), "ok", 0))


def _not_null(conn, table: str, column: str) -> bool:
    row = _one(conn, """SELECT is_nullable FROM information_schema.columns WHERE table_schema = 'public'
        AND table_name = %s AND column_name = %s""", (table, column))
    return _value(row, "is_nullable", 0) == "NO"


def orphan_report(conn) -> Dict[str, int]:
    """Counts of rows that block the constraints (only for checks whose columns exist)."""
    report = {}
    for label, query in ORPHAN_CHECKS.items():
        row = _one(conn, query)
        report[label] = int(_value(row, "count", 0))
    return report


def build_plan(conn) -> Plan:
    """Idempotent plan; raises ProvisioningError while blocking rows exist."""
    who = _one(conn, "SELECT current_user AS u, (SELECT rolsuper FROM pg_roles WHERE rolname = current_user) AS s")
    owner = _value(_one(conn, """SELECT pg_get_userbyid(c.relowner) AS owner FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'public' AND c.relname = 'messages'"""),
                   "owner", 0)
    if not (_value(who, "s", 1) or _value(who, "u", 0) == owner):
        raise ProvisioningError("Run migration 007 as the owner of the application tables (or a superuser)")
    blocking = {k: v for k, v in orphan_report(conn).items() if v}
    if blocking:
        raise ProvisioningError("Rows would violate the new constraints; fix them first (nothing was changed): "
                                + "; ".join(f"{k}: {v}" for k, v in blocking.items()))
    plan = Plan()
    for table, column, kind in COLUMNS:
        if not _column_exists(conn, table, column):
            plan.add(f"add {table}.{column}", sql.SQL("ALTER TABLE {} ADD COLUMN {} {}").format(
                sql.Identifier("public", table), sql.Identifier(column), sql.SQL(kind)))
    if not _not_null(conn, "feedback", "message_id"):
        plan.add("feedback.message_id is required", sql.SQL("ALTER TABLE public.feedback ALTER COLUMN message_id SET NOT NULL"))
    for name, (table, definition) in CONSTRAINTS.items():
        if not _constraint_exists(conn, name):
            plan.add(f"{table}: {name}", sql.SQL("ALTER TABLE {} ADD CONSTRAINT {} {}").format(
                sql.Identifier("public", table), sql.Identifier(name), sql.SQL(definition)))
    for name, (table, column) in INDEXES.items():
        if _index_exists(conn, name):
            continue
        plan.add(f"index {name}", sql.SQL("CREATE INDEX IF NOT EXISTS {} ON {} ({})").format(
            sql.Identifier(name), sql.Identifier("public", table), sql.Identifier(column)))
    return plan


def verify(conn) -> Dict[str, object]:
    """Read-only report of the integrity state."""
    problems: List[str] = []
    for table, column, _ in COLUMNS:
        if not _column_exists(conn, table, column):
            problems.append(f"missing column {table}.{column}")
    if not _not_null(conn, "feedback", "message_id"):
        problems.append("feedback.message_id is nullable")
    for name in CONSTRAINTS:
        if not _constraint_exists(conn, name):
            problems.append(f"missing constraint {name}")
    for name in INDEXES:
        if not _index_exists(conn, name):
            problems.append(f"missing index {name}")
    orphans = orphan_report(conn)
    problems += [f"{k}: {v}" for k, v in orphans.items() if v]
    return {"problems": problems, "orphans": orphans}
