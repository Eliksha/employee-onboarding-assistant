"""Chat history, feedback, escalations and shared checklist storage."""
import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from backend.config import settings
from backend.services.auth_schema import AUTH_TABLES, SQLITE_DDL
from backend.services.employee_db import UnknownEmployeeError
from backend.services.postgres import postgres_connection

logger = logging.getLogger("app")


def _postgres() -> bool:
    backend = settings.db_backend.strip().lower()
    if backend not in {"sqlite", "postgresql"}:
        raise ValueError(f"Unsupported DB_BACKEND: {backend}")
    return backend == "postgresql"


@contextmanager
def _conn():
    if _postgres():
        with postgres_connection() as con:
            yield con
        return
    path = Path(settings.db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def _execute(con, query, params=(), *, one=False, all_rows=False):
    if _postgres():
        with con.cursor() as cur:
            cur.execute(query.replace("?", "%s"), params)
            if one:
                return cur.fetchone()
            if all_rows:
                return cur.fetchall()
            return cur.rowcount
    cur = con.execute(query, params)
    if one:
        return cur.fetchone()
    if all_rows:
        return cur.fetchall()
    return cur.rowcount


def _insert_id(con, query, params):
    if _postgres():
        with con.cursor() as cur:
            cur.execute(query.replace("?", "%s") + " RETURNING id", params)
            return cur.fetchone()["id"]
    return con.execute(query, params).lastrowid


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def check_database() -> bool:
    """Lightweight readiness probe for /health: True if the configured database answers `SELECT 1`.

    Uses a short connect and statement timeout (HEALTH_DB_TIMEOUT_SECONDS). Never creates a database
    file and never logs connection details - only the exception type.
    """
    timeout = max(1, int(settings.health_db_timeout_seconds))
    try:
        if _postgres():
            with postgres_connection(connect_timeout=timeout) as con:
                with con.cursor() as cur:
                    cur.execute("SET statement_timeout = %s", (timeout * 1000,))
                    cur.execute("SELECT 1 AS ok")
                    cur.fetchone()
        else:
            path = Path(settings.db_path)
            if not path.is_file():
                raise FileNotFoundError("SQLite database file not found")
            con = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=timeout)
            try:
                con.execute("SELECT 1").fetchone()
            finally:
                con.close()
        return True
    except Exception as exc:  # any failure means "not ready"; details stay out of logs and responses
        logger.warning("health check: database unavailable (%s)", type(exc).__name__)
        return False


def init_db() -> None:
    if _postgres():
        # PostgreSQL schema and seed data are migrated explicitly (never altered implicitly at startup).
        with _conn() as con:
            _execute(con, "SELECT 1 FROM employees LIMIT 1", one=True)
            present = _execute(con, """SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name IN ('user_accounts', 'user_sessions')""", all_rows=True)
        if len(present) != len(AUTH_TABLES):
            raise RuntimeError(
                "Authentication tables are missing in PostgreSQL. Run: python backend/migrations/004_auth_tables.py "
                "(with PYTHONPATH set to the project root)."
            )
        return
    with _conn() as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY AUTOINCREMENT, question TEXT, answer TEXT,
                found INTEGER, sources TEXT, created_at TEXT);
            CREATE TABLE IF NOT EXISTS feedback(id INTEGER PRIMARY KEY AUTOINCREMENT, message_id INTEGER, rating TEXT,
                comment TEXT, created_at TEXT);
            CREATE TABLE IF NOT EXISTS escalations(id INTEGER PRIMARY KEY AUTOINCREMENT, question TEXT, contact_pref TEXT,
                status TEXT, created_at TEXT);
            CREATE TABLE IF NOT EXISTS checklist(id INTEGER PRIMARY KEY, phase TEXT, task TEXT, done INTEGER);
        """)
        c.executescript(SQLITE_DDL)
        if c.execute("SELECT COUNT(*) FROM checklist").fetchone()[0] == 0:
            seed = Path(settings.raw_dir) / "checklist.json"
            if seed.exists():
                for it in json.loads(seed.read_text(encoding="utf-8")):
                    c.execute("INSERT INTO checklist VALUES (?,?,?,?)", (it["id"], it["phase"], it["task"], int(it["done"])))


def save_message(question: str, answer: str, found: bool, sources: List[Dict]) -> int:
    init_db()
    with _conn() as c:
        return _insert_id(c, "INSERT INTO messages(question, answer, found, sources, created_at) VALUES (?,?,?,?,?)",
                          (question, answer, int(found), json.dumps(sources), _now()))


def get_message_owner(message_id: int) -> tuple[bool, Optional[str]]:
    """Return (exists, employee_id) for a chat message; employee_id is None for legacy/global messages."""
    with _conn() as c:
        row = _execute(c, "SELECT employee_id FROM messages WHERE id = ?", (message_id,), one=True)
    return (row is not None, row["employee_id"] if row is not None else None)


def message_exists(message_id: int) -> bool:
    init_db()
    with _conn() as c:
        return _execute(c, "SELECT 1 FROM messages WHERE id=?", (message_id,), one=True) is not None


def _message_dict(row):
    result = dict(row)
    result["found"] = bool(result["found"])
    sources = result.get("sources")
    result["sources"] = json.loads(sources or "[]") if isinstance(sources, str) or sources is None else sources
    return result


def recent_messages(limit: int = 20) -> List[Dict]:
    init_db()
    with _conn() as c:
        rows = _execute(c, "SELECT * FROM messages ORDER BY id DESC LIMIT ?", (limit,), all_rows=True)
    return [_message_dict(r) for r in rows]


def get_checklist() -> List[Dict]:
    init_db()
    with _conn() as c:
        rows = _execute(c, "SELECT * FROM checklist ORDER BY id", all_rows=True)
    return [{**dict(r), "done": bool(r["done"])} for r in rows]


def set_checklist_done(item_id: int, done: bool) -> Optional[Dict]:
    init_db()
    with _conn() as c:
        count = _execute(c, "UPDATE checklist SET done=? WHERE id=?", (int(done), item_id))
        if count == 0:
            return None
        r = _execute(c, "SELECT * FROM checklist WHERE id=?", (item_id,), one=True)
    return {**dict(r), "done": bool(r["done"])}


def add_feedback(message_id: int, rating: str, comment: Optional[str]) -> int:
    init_db()
    with _conn() as c:
        return _insert_id(c, "INSERT INTO feedback(message_id, rating, comment, created_at) VALUES (?,?,?,?)",
                          (message_id, rating, comment, _now()))


def add_escalation(question: str, contact_pref: Optional[str]) -> int:
    init_db()
    with _conn() as c:
        return _insert_id(c, "INSERT INTO escalations(question, contact_pref, status, created_at) VALUES (?,?,?,?)",
                          (question, contact_pref, "open", _now()))


def save_employee_message(employee_id: str, question: str, answer: str, found: bool, sources: List[Dict]) -> int:
    """Save a message associated with a fictional employee."""
    with _conn() as c:
        employee = _execute(c, "SELECT 1 FROM employees WHERE employee_id = ?", (employee_id,), one=True)
        if employee is None:
            raise UnknownEmployeeError("Unknown employee ID")
        return _insert_id(c, """INSERT INTO messages
            (employee_id, question, answer, found, sources, created_at) VALUES (?, ?, ?, ?, ?, ?)""",
            (employee_id, question, answer, int(found), json.dumps(sources), _now()))


def recent_employee_messages(employee_id: str, limit: int = 20) -> List[Dict]:
    """Retrieve only the selected fictional employee's messages."""
    limit = max(1, min(limit, 100))
    with _conn() as c:
        employee = _execute(c, "SELECT 1 FROM employees WHERE employee_id = ?", (employee_id,), one=True)
        if employee is None:
            raise UnknownEmployeeError("Unknown employee ID")
        rows = _execute(c, """SELECT * FROM messages WHERE employee_id = ?
            ORDER BY id DESC LIMIT ?""", (employee_id, limit), all_rows=True)
    return [_message_dict(row) for row in rows]
