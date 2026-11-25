
"""Migration 003: Add employee-specific chat history support."""

import sqlite3
from pathlib import Path

from backend.config import settings


def migrate(db_path=None):
    """Add employee_id without deleting existing messages."""

    path = Path(db_path or settings.db_path).resolve()

    if not path.is_file():
        raise FileNotFoundError(
            f"Database not found: {path}"
        )

    conn = sqlite3.connect(str(path))

    try:
        columns = {
            row[1]
            for row in conn.execute(
                "PRAGMA table_info(messages)"
            )
        }

        if not columns:
            raise RuntimeError(
                "Messages table does not exist"
            )

        if "employee_id" not in columns:
            conn.execute(
                "ALTER TABLE messages "
                "ADD COLUMN employee_id TEXT"
            )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_messages_employee_id
            ON messages(employee_id, id DESC)
            """
        )

        conn.commit()

        print(
            "Migration 003 completed successfully."
        )

    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
