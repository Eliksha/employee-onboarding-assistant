"""Chat history, feedback, escalations and shared checklist storage."""
import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from backend.config import settings
from backend.services import db_integrity, employee_scope, hr_queue_schema, postgres
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


LEAST_PRIVILEGE_HINT = "Provision roles with backend/migrations/005_least_privilege_roles.py (see docs/runbook.md)."


PRIVILEGED_CONNECTION = (
    "Refusing to start: the application is configured to connect to PostgreSQL as a privileged role "
    "({flags}). Use the least-privilege application role (PG_USER=onboardai_app). In Docker, start the stack "
    "with the secrets file (docker compose --env-file <secrets file> ...). "
)


def privileged_override_allowed() -> bool:
    """ALLOW_PRIVILEGED_DB_CONNECTION is honoured only for local development (never in production/Docker)."""
    return settings.allow_privileged_db_connection and settings.app_env.strip().lower() == "development"


def enforce_role_policy(app_is_superuser: bool, app_bypasses_rls: bool = False) -> list[str]:
    """PostgreSQL role hygiene at startup. Returns the issues that only warrant a warning.

    Fails closed: a superuser or BYPASSRLS application role is refused in every environment unless
    ALLOW_PRIVILEGED_DB_CONNECTION=true is set explicitly with APP_ENV=development (local runs only).
    """
    if settings.pg_reader_user.strip() and len(settings.pg_scope_secret) < employee_scope.MIN_SECRET_LENGTH:
        # Without the signing secret every employee-scoped read would fail closed: refuse to start.
        raise RuntimeError(f"PG_READER_USER is set but PG_SCOPE_SECRET is missing or shorter than "
                           f"{employee_scope.MIN_SECRET_LENGTH} characters. {LEAST_PRIVILEGE_HINT}")
    issues = []
    flags = [name for name, on in (("superuser", app_is_superuser), ("BYPASSRLS", app_bypasses_rls)) if on]
    if flags:
        if not privileged_override_allowed():
            raise RuntimeError(PRIVILEGED_CONNECTION.format(flags=", ".join(flags)) + LEAST_PRIVILEGE_HINT)
        issues.append("the application connects to PostgreSQL as a superuser"
                      if app_is_superuser else "the application role can bypass row-level security")
        logger.warning("ALLOW_PRIVILEGED_DB_CONNECTION=true (development only): privileged database role allowed")
    if not settings.pg_reader_user.strip():
        issues.append("no dedicated read-only role (PG_READER_USER) is configured for SQL-agent queries")
    if issues and settings.app_env.strip().lower() == "production":
        raise RuntimeError("Unsafe database configuration: " + "; ".join(issues) + ". " + LEAST_PRIVILEGE_HINT)
    for issue in issues:
        logger.warning("database least-privilege check: %s. %s", issue, LEAST_PRIVILEGE_HINT)
    return issues


_VERIFIED_CONFIGS: set = set()


def _postgres_config_key() -> tuple:
    """Settings that decide the outcome of the startup checks (no secret values, only their presence/length)."""
    return (settings.pg_host, settings.pg_port, settings.pg_database, settings.pg_user, settings.pg_reader_user,
            len(settings.pg_scope_secret), settings.pg_sslmode, settings.pg_sslrootcert, settings.app_env,
            settings.allow_privileged_db_connection)


def init_db() -> None:
    if _postgres():
        key = _postgres_config_key()
        if key in _VERIFIED_CONFIGS:
            return  # checks already passed for this configuration in this process (migrations need a restart)
        verify_postgres_startup()
        _VERIFIED_CONFIGS.add(key)
        return
    _init_sqlite()


def verify_postgres_startup() -> None:
    """Fail-closed PostgreSQL startup checks (schema is migrated explicitly, never altered implicitly).

    TLS settings, authentication tables, migration 007 (every column, constraint and index), migration 008
    (HR/IT queue and shared rate-limit objects) and the role policy (no superuser / BYPASSRLS).
    """
    postgres.validate_tls_settings()
    with _conn() as con:
        _execute(con, "SELECT 1 FROM employees LIMIT 1", one=True)
        present = _execute(con, """SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name IN ('user_accounts', 'user_sessions')""", all_rows=True)
        role = _execute(con, "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user",
                        one=True)
        integrity = _execute(con, """SELECT 1 FROM information_schema.columns WHERE table_schema = 'public'
            AND table_name = 'escalations' AND column_name = 'employee_id'""", one=True)
        integrity_problems = db_integrity.schema_problems(con) if integrity is not None else []
        missing_008 = hr_queue_schema.missing_objects(con)
    if len(present) != len(AUTH_TABLES):
        raise RuntimeError(
            "Authentication tables are missing in PostgreSQL. Run: python backend/migrations/004_auth_tables.py "
            "(with PYTHONPATH set to the project root)."
        )
    if integrity is None:
        raise RuntimeError(
            "Data-integrity migration 007 has not been applied to PostgreSQL. Run: "
            "python backend/migrations/007_data_integrity.py --apply (see docs/runbook.md section 11)."
        )
    if integrity_problems:
        raise RuntimeError("Data-integrity migration 007 is incomplete (" + "; ".join(integrity_problems) + "). "
                           "Run: python backend/migrations/007_data_integrity.py --verify, then --apply.")
    if missing_008:
        raise RuntimeError("Migration 008 (HR/IT escalation queue, shared login rate limiting) has not been applied "
                           "(missing: " + ", ".join(missing_008) + "). Run: python backend/migrations/"
                           "008_hr_escalation_queue.py --apply (see docs/runbook.md section 14).")
    if role is None:  # current_user always has a pg_roles row; anything else is treated as privileged
        raise RuntimeError("Could not determine the PostgreSQL role attributes of the application connection.")
    enforce_role_policy(app_is_superuser=bool(role["rolsuper"]), app_bypasses_rls=bool(role["rolbypassrls"]))


def _init_sqlite() -> None:
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
        # M5 attribution columns (PostgreSQL: migration 007 / docker/postgres/04_integrity.sql).
        columns = {r[1] for r in c.execute("PRAGMA table_info(escalations)")}
        if "employee_id" not in columns:
            c.execute("ALTER TABLE escalations ADD COLUMN employee_id TEXT REFERENCES employees(employee_id)")
        if "message_id" not in columns:
            c.execute("ALTER TABLE escalations ADD COLUMN message_id INTEGER REFERENCES messages(id) ON DELETE SET NULL")
        # Migration 008 (HR/IT queue, audit trail, shared login rate limiting): PostgreSQL uses 05_hr_queue.sql / 008.
        for column, definition in hr_queue_schema.ESCALATION_COLUMNS:
            if column not in columns:
                c.execute(f"ALTER TABLE escalations ADD COLUMN {column} {definition}")
        c.executescript(hr_queue_schema.SQLITE_DDL)
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
    if "escalated" in result:
        result["escalated"] = bool(result["escalated"])
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


def add_escalation(question: str, contact_pref: Optional[str], employee_id: Optional[str] = None,
                   message_id: Optional[int] = None, actor_user_id: Optional[int] = None) -> int:
    """Put an escalation in the HR/IT queue, attributed to the session employee (None for admin accounts).

    The queue entry and its 'created' audit event are written in one transaction.
    """
    init_db()
    with _conn() as c:
        escalation_id = _insert_id(c, """INSERT INTO escalations(question, contact_pref, status, created_at, employee_id,
            message_id) VALUES (?,?,?,?,?,?)""", (question, contact_pref, "open", _now(), employee_id, message_id))
        _add_event(c, escalation_id, actor_user_id, "created", None, "open")
        return escalation_id


def find_escalation(message_id: int) -> Optional[int]:
    """ID of an existing escalation of this chat message (escalating the same answer twice is idempotent)."""
    with _conn() as c:
        row = _execute(c, "SELECT id FROM escalations WHERE message_id = ? ORDER BY id LIMIT 1", (message_id,), one=True)
    return row["id"] if row is not None else None


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
        # Latest rating and escalation state per message (optional fields; the chat UI shows them).
        rows = _execute(c, """SELECT m.*,
            (SELECT f.rating FROM feedback f WHERE f.message_id = m.id ORDER BY f.id DESC LIMIT 1) AS feedback,
            EXISTS (SELECT 1 FROM escalations e WHERE e.message_id = m.id) AS escalated,
            (SELECT e.status FROM escalations e WHERE e.message_id = m.id ORDER BY e.id LIMIT 1) AS escalation_status
            FROM messages m WHERE m.employee_id = ? ORDER BY m.id DESC LIMIT ?""", (employee_id, limit), all_rows=True)
    return [_message_dict(row) for row in rows]


# ---------------------------------------------------------------- HR/IT escalation queue (migration 008)
class EscalationNotFound(LookupError):
    pass


class InvalidTransition(ValueError):
    pass


# Fields HR/IT staff see: the escalated question, who raised it (employee ID and name only), the escalated answer
# (only that one message, never the employee's wider chat history), status and handling. No feedback comments,
# no records data, no account details.
_QUEUE_SELECT = """SELECT e.id, e.question, e.contact_pref, e.status, e.created_at, e.updated_at, e.resolution_note,
    e.employee_id, emp.name AS employee_name, e.message_id, m.answer AS escalated_answer, m.sources AS answer_sources,
    ua.email AS handled_by
    FROM escalations e
    LEFT JOIN employees emp ON emp.employee_id = e.employee_id
    LEFT JOIN messages m ON m.id = e.message_id
    LEFT JOIN user_accounts ua ON ua.id = e.handled_by"""


def _escalation_dict(row) -> Dict:
    result = dict(row)
    sources = result.pop("answer_sources", None)
    result["answer_sources"] = json.loads(sources) if isinstance(sources, str) and sources else (sources or [])
    return result


def _add_event(c, escalation_id: int, actor_user_id: Optional[int], action: str,
               from_status: Optional[str] = None, to_status: Optional[str] = None, note: Optional[str] = None) -> None:
    _insert_id(c, """INSERT INTO escalation_events(escalation_id, actor_user_id, action, from_status, to_status, note,
        created_at) VALUES (?,?,?,?,?,?,?)""", (escalation_id, actor_user_id, action, from_status, to_status, note, _now()))


def list_escalations(status: Optional[str] = None, limit: int = 100) -> List[Dict]:
    """HR/IT queue: newest first, optionally filtered by status."""
    limit = max(1, min(int(limit), 200))
    with _conn() as c:
        if status:
            rows = _execute(c, _QUEUE_SELECT + " WHERE e.status = ? ORDER BY e.id DESC LIMIT ?", (status, limit),
                            all_rows=True)
        else:
            rows = _execute(c, _QUEUE_SELECT + " ORDER BY e.id DESC LIMIT ?", (limit,), all_rows=True)
    return [_escalation_dict(r) for r in rows]


def get_escalation(escalation_id: int, viewer_user_id: Optional[int] = None) -> Dict:
    """One escalation with its audit trail; records a 'viewed' event for the viewer (access audit)."""
    with _conn() as c:
        row = _execute(c, _QUEUE_SELECT + " WHERE e.id = ?", (escalation_id,), one=True)
        if row is None:
            raise EscalationNotFound(escalation_id)
        if viewer_user_id is not None:
            _add_event(c, escalation_id, viewer_user_id, "viewed")
        events = _execute(c, """SELECT ev.id, ev.action, ev.from_status, ev.to_status, ev.note, ev.created_at,
            ua.email AS actor FROM escalation_events ev LEFT JOIN user_accounts ua ON ua.id = ev.actor_user_id
            WHERE ev.escalation_id = ? ORDER BY ev.id""", (escalation_id,), all_rows=True)
    result = _escalation_dict(row)
    result["events"] = [dict(e) for e in events]
    return result


def update_escalation_status(escalation_id: int, to_status: str, actor_user_id: int,
                             note: Optional[str] = None) -> Dict:
    """Move an escalation along the workflow (hr_queue_schema.ESCALATION_TRANSITIONS); audited in one transaction."""
    if to_status not in hr_queue_schema.ESCALATION_TRANSITIONS:
        raise InvalidTransition(f"Unknown status: {to_status}")
    note = (note or "").strip() or None
    with _conn() as c:
        row = _execute(c, "SELECT status FROM escalations WHERE id = ?", (escalation_id,), one=True)
        if row is None:
            raise EscalationNotFound(escalation_id)
        current = row["status"] or "open"
        if to_status not in hr_queue_schema.ESCALATION_TRANSITIONS.get(current, ()):
            raise InvalidTransition(f"Cannot change status from {current} to {to_status}")
        # Optimistic check on the current status: a concurrent change makes this update affect no row.
        changed = _execute(c, """UPDATE escalations SET status = ?, updated_at = ?, handled_by = ?,
            resolution_note = COALESCE(?, resolution_note) WHERE id = ? AND status = ?""",
                           (to_status, _now(), actor_user_id, note, escalation_id, current))
        if changed != 1:
            raise InvalidTransition("The escalation was changed by someone else; reload and try again")
        _add_event(c, escalation_id, actor_user_id, "status_changed", current, to_status, note)
    return get_escalation(escalation_id)
