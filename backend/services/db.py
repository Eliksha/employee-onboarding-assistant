"""Small SQLite layer: chat history, feedback, escalations and the onboarding checklist."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from backend.config import settings


@contextmanager
def _conn():
    path = Path(settings.db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def init_db() -> None:
    with _conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY AUTOINCREMENT, question TEXT, answer TEXT,
                found INTEGER, sources TEXT, created_at TEXT);
            CREATE TABLE IF NOT EXISTS feedback(id INTEGER PRIMARY KEY AUTOINCREMENT, message_id INTEGER, rating TEXT,
                comment TEXT, created_at TEXT);
            CREATE TABLE IF NOT EXISTS escalations(id INTEGER PRIMARY KEY AUTOINCREMENT, question TEXT, contact_pref TEXT,
                status TEXT, created_at TEXT);
            CREATE TABLE IF NOT EXISTS checklist(id INTEGER PRIMARY KEY, phase TEXT, task TEXT, done INTEGER);
            """
        )
        if c.execute("SELECT COUNT(*) FROM checklist").fetchone()[0] == 0:
            seed = Path(settings.raw_dir) / "checklist.json"
            if seed.exists():
                for it in json.loads(seed.read_text(encoding="utf-8")):
                    c.execute("INSERT INTO checklist VALUES (?,?,?,?)", (it["id"], it["phase"], it["task"], int(it["done"])))


def save_message(question: str, answer: str, found: bool, sources: List[Dict]) -> int:
    init_db()
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO messages(question, answer, found, sources, created_at) VALUES (?,?,?,?,?)",
            (question, answer, int(found), json.dumps(sources), _now()),
        )
        return cur.lastrowid


def message_exists(message_id: int) -> bool:
    init_db()
    with _conn() as c:
        return c.execute("SELECT 1 FROM messages WHERE id=?", (message_id,)).fetchone() is not None


def recent_messages(limit: int = 20) -> List[Dict]:
    init_db()
    with _conn() as c:
        rows = c.execute("SELECT * FROM messages ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [{**dict(r), "found": bool(r["found"]), "sources": json.loads(r["sources"] or "[]")} for r in rows]


def get_checklist() -> List[Dict]:
    init_db()
    with _conn() as c:
        rows = c.execute("SELECT * FROM checklist ORDER BY id").fetchall()
    return [{**dict(r), "done": bool(r["done"])} for r in rows]


def set_checklist_done(item_id: int, done: bool) -> Optional[Dict]:
    init_db()
    with _conn() as c:
        cur = c.execute("UPDATE checklist SET done=? WHERE id=?", (int(done), item_id))
        if cur.rowcount == 0:
            return None
        r = c.execute("SELECT * FROM checklist WHERE id=?", (item_id,)).fetchone()
    return {**dict(r), "done": bool(r["done"])}


def add_feedback(message_id: int, rating: str, comment: Optional[str]) -> int:
    init_db()
    with _conn() as c:
        return c.execute(
            "INSERT INTO feedback(message_id, rating, comment, created_at) VALUES (?,?,?,?)",
            (message_id, rating, comment, _now()),
        ).lastrowid


def add_escalation(question: str, contact_pref: Optional[str]) -> int:
    init_db()
    with _conn() as c:
        return c.execute(
            "INSERT INTO escalations(question, contact_pref, status, created_at) VALUES (?,?,?,?)",
            (question, contact_pref, "open", _now()),
        ).lastrowid
