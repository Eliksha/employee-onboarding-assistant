
"""Migration 001: Add synthetic employee-support tables."""

import sqlite3
from contextlib import closing
from pathlib import Path


def migrate(db_path: str | Path) -> None:
    """Create new tables without modifying existing tables."""
    db_path = Path(db_path)

    if not db_path.is_file():
        raise FileNotFoundError(f"Database not found: {db_path}")

    with closing(sqlite3.connect(str(db_path))) as conn:
        with conn:
            conn.execute("PRAGMA foreign_keys = ON")

        conn.executescript("""
            CREATE TABLE IF NOT EXISTS employees (
                employee_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                department TEXT NOT NULL,
                joining_date TEXT NOT NULL,
                location TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS leave_balances (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id TEXT NOT NULL,
                leave_type TEXT NOT NULL,
                available_days REAL NOT NULL DEFAULT 0
                    CHECK (available_days >= 0),
                FOREIGN KEY (employee_id)
                    REFERENCES employees(employee_id),
                UNIQUE (employee_id, leave_type)
            );

            CREATE TABLE IF NOT EXISTS assets (
                asset_id TEXT PRIMARY KEY,
                employee_id TEXT NOT NULL,
                asset_type TEXT NOT NULL,
                asset_name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'assigned',
                FOREIGN KEY (employee_id)
                    REFERENCES employees(employee_id)
            );

            CREATE TABLE IF NOT EXISTS payroll_calendar (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                payroll_month TEXT NOT NULL UNIQUE,
                payment_date TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'scheduled'
            );

            CREATE TABLE IF NOT EXISTS tickets (
                ticket_id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id TEXT NOT NULL,
                category TEXT NOT NULL,
                subject TEXT NOT NULL,
                description TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL
                    DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL
                    DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (employee_id)
                    REFERENCES employees(employee_id)
            );

            CREATE TABLE IF NOT EXISTS checklist_assignments (
                employee_id TEXT NOT NULL,
                checklist_id INTEGER NOT NULL,
                done INTEGER NOT NULL DEFAULT 0
                    CHECK (done IN (0, 1)),
                PRIMARY KEY (employee_id, checklist_id),
                FOREIGN KEY (employee_id)
                    REFERENCES employees(employee_id),
                FOREIGN KEY (checklist_id)
                    REFERENCES checklist(id)
            );
        """)


if __name__ == "__main__":
    migrate(Path(__file__).resolve().parents[2] / "data" / "app.db")
    print("Migration 001 completed successfully.")
