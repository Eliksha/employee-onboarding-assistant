"""Employee-specific database operations for OnboardAI (SQLite/PostgreSQL)."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from backend.config import settings
from backend.services.postgres import postgres_connection


class UnknownEmployeeError(ValueError):
    """The requested demo employee does not exist (a client error, unlike other ValueErrors)."""


def _postgres() -> bool:
    backend = settings.db_backend.strip().lower()
    if backend not in {"sqlite", "postgresql"}:
        raise ValueError(f"Unsupported DB_BACKEND: {backend}")
    return backend == "postgresql"


@contextmanager
def _connection(*, readonly: bool):
    if _postgres():
        with postgres_connection() as conn:
            yield conn
        return
    db_path = Path(settings.db_path).resolve()
    if not db_path.is_file():
        raise FileNotFoundError(f"Database not found: {db_path}")
    if readonly:
        conn = sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        if not readonly:
            conn.commit()
    except Exception:
        if not readonly:
            conn.rollback()
        raise
    finally:
        conn.close()


def _execute(conn, query, params=(), *, one=False, all_rows=False):
    if _postgres():
        with conn.cursor() as cur:
            cur.execute(query.replace("?", "%s"), params)
            if one:
                return cur.fetchone()
            if all_rows:
                return cur.fetchall()
            return cur.rowcount
    cur = conn.execute(query, params)
    if one:
        return cur.fetchone()
    if all_rows:
        return cur.fetchall()
    return cur.rowcount


def _rows(query, params=()):
    with _connection(readonly=True) as conn:
        return _execute(conn, query, params, all_rows=True)


def get_employee(employee_id: str) -> Optional[dict]:
    """Retrieve a fictional employee's profile."""
    with _connection(readonly=True) as conn:
        row = _execute(conn, """SELECT employee_id, name, email, department,
            joining_date, location FROM employees WHERE employee_id = ?""", (employee_id,), one=True)
    return dict(row) if row else None


def get_leave_balances(employee_id: str) -> list[dict]:
    rows = _rows("""SELECT leave_type, available_days FROM leave_balances
        WHERE employee_id = ? ORDER BY leave_type""", (employee_id,))
    return [dict(row) for row in rows]


def get_employee_assets(employee_id: str) -> list[dict]:
    rows = _rows("""SELECT asset_id, asset_type, asset_name, status FROM assets
        WHERE employee_id = ? ORDER BY asset_id""", (employee_id,))
    return [dict(row) for row in rows]


def get_payroll_calendar() -> list[dict]:
    rows = _rows("""SELECT payroll_month, payment_date, status FROM payroll_calendar
        ORDER BY payment_date""")
    return [dict(row) for row in rows]


def get_employee_checklist(employee_id: str) -> list[dict]:
    rows = _rows("""SELECT c.id, c.phase, c.task, ca.done
        FROM checklist_assignments AS ca JOIN checklist AS c ON c.id = ca.checklist_id
        WHERE ca.employee_id = ? ORDER BY c.id""", (employee_id,))
    return [{**dict(row), "done": bool(row["done"])} for row in rows]


def get_employee_tickets(employee_id: str) -> list[dict]:
    rows = _rows("""SELECT ticket_id, category, subject, description, status,
        created_at, updated_at FROM tickets WHERE employee_id = ?
        ORDER BY created_at DESC, ticket_id DESC""", (employee_id,))
    return [dict(row) for row in rows]


def update_employee_checklist(employee_id: str, item_id: int, done: bool) -> Optional[dict]:
    """Update one employee's onboarding checklist item."""
    with _connection(readonly=False) as conn:
        count = _execute(conn, """UPDATE checklist_assignments SET done = ?
            WHERE employee_id = ? AND checklist_id = ?""", (int(done), employee_id, item_id))
        if count == 0:
            return None
        row = _execute(conn, """SELECT c.id, c.phase, c.task, ca.done
            FROM checklist_assignments AS ca JOIN checklist AS c ON c.id = ca.checklist_id
            WHERE ca.employee_id = ? AND ca.checklist_id = ?""", (employee_id, item_id), one=True)
    return {**dict(row), "done": bool(row["done"])}


def create_employee_ticket(employee_id: str, category: str, subject: str, description: str) -> dict:
    """Create a support ticket for a fictional employee."""
    with _connection(readonly=False) as conn:
        query = """INSERT INTO tickets (employee_id, category, subject, description, status)
            VALUES (?, ?, ?, ?, 'open')"""
        params = (employee_id, category, subject, description)
        if _postgres():
            with conn.cursor() as cur:
                cur.execute(query.replace("?", "%s") + " RETURNING ticket_id", params)
                ticket_id = cur.fetchone()["ticket_id"]
        else:
            ticket_id = conn.execute(query, params).lastrowid
        row = _execute(conn, """SELECT ticket_id, employee_id, category, subject,
            description, status, created_at, updated_at FROM tickets WHERE ticket_id = ?""",
            (ticket_id,), one=True)
    return dict(row)
