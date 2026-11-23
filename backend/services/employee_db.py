"""Employee-specific database operations for OnboardAI (SQLite/PostgreSQL).

Reads go through `readonly_query.fetch_readonly` (SQL-agent path: READ ONLY transaction, statement
timeout, row limit, least-privilege reader role and employee-scoped row-level security on PostgreSQL).
Writes (checklist updates, ticket creation) use the application's read-write connection.
"""
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from backend.config import settings
from backend.services.postgres import postgres_connection
from backend.services.readonly_query import fetch_readonly


class UnknownEmployeeError(ValueError):
    """The requested demo employee does not exist (a client error, unlike other ValueErrors)."""


def _postgres() -> bool:
    backend = settings.db_backend.strip().lower()
    if backend not in {"sqlite", "postgresql"}:
        raise ValueError(f"Unsupported DB_BACKEND: {backend}")
    return backend == "postgresql"


@contextmanager
def _write_connection():
    """Application read-write connection (commit on success, rollback on error)."""
    if _postgres():
        with postgres_connection() as conn:
            yield conn
        return
    db_path = Path(settings.db_path).resolve()
    if not db_path.is_file():
        raise FileNotFoundError(f"Database not found: {db_path}")
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
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


def _rows(query, params=(), *, employee_id: Optional[str] = None) -> list[dict]:
    """Read-only rows; `employee_id` scopes row-level security on PostgreSQL (defence in depth)."""
    return fetch_readonly(query, params, scope_employee_id=employee_id).rows


def get_employee(employee_id: str) -> Optional[dict]:
    """Retrieve a fictional employee's profile."""
    rows = _rows("""SELECT employee_id, name, email, department,
        joining_date, location FROM employees WHERE employee_id = ?""", (employee_id,), employee_id=employee_id)
    return rows[0] if rows else None


def get_leave_balances(employee_id: str) -> list[dict]:
    return _rows("""SELECT leave_type, available_days FROM leave_balances
        WHERE employee_id = ? ORDER BY leave_type""", (employee_id,), employee_id=employee_id)


def get_employee_assets(employee_id: str) -> list[dict]:
    return _rows("""SELECT asset_id, asset_type, asset_name, status FROM assets
        WHERE employee_id = ? ORDER BY asset_id""", (employee_id,), employee_id=employee_id)


def get_payroll_calendar() -> list[dict]:
    return _rows("""SELECT payroll_month, payment_date, status FROM payroll_calendar
        ORDER BY payment_date""")


def get_employee_checklist(employee_id: str) -> list[dict]:
    rows = _rows("""SELECT c.id, c.phase, c.task, ca.done
        FROM checklist_assignments AS ca JOIN checklist AS c ON c.id = ca.checklist_id
        WHERE ca.employee_id = ? ORDER BY c.id""", (employee_id,), employee_id=employee_id)
    return [{**dict(row), "done": bool(row["done"])} for row in rows]


def get_employee_tickets(employee_id: str) -> list[dict]:
    return _rows("""SELECT ticket_id, category, subject, description, status,
        created_at, updated_at FROM tickets WHERE employee_id = ?
        ORDER BY created_at DESC, ticket_id DESC""", (employee_id,), employee_id=employee_id)


def update_employee_checklist(employee_id: str, item_id: int, done: bool) -> Optional[dict]:
    """Update one employee's onboarding checklist item."""
    with _write_connection() as conn:
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
    with _write_connection() as conn:
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
