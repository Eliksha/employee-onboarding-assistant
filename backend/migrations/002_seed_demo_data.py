
"""Seed synthetic employee data for the OnboardAI demo."""

import sqlite3
from contextlib import closing
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "app.db"


def seed_demo_data(db_path: Path = DB_PATH) -> None:
    if not db_path.is_file():
        raise FileNotFoundError(f"Database not found: {db_path}")

    with closing(sqlite3.connect(str(db_path))) as conn:
        conn.execute("PRAGMA foreign_keys = ON")

        with conn:
            employees = [
                (
                    "EMP001", "Aarav Sharma",
                    "aarav.sharma@example.com",
                    "Technology", "2026-11-02", "Pune"
                ),
                (
                    "EMP002", "Meera Iyer",
                    "meera.iyer@example.com",
                    "Human Resources", "2026-11-09", "Bengaluru"
                ),
                (
                    "EMP003", "Rohan Verma",
                    "rohan.verma@example.com",
                    "Finance", "2026-11-16", "Hyderabad"
                ),
            ]

            conn.executemany(
                """
                INSERT OR IGNORE INTO employees
                (employee_id, name, email, department,
                 joining_date, location)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                employees,
            )

            leave_balances = [
                ("EMP001", "Casual Leave", 8),
                ("EMP001", "Sick Leave", 6),
                ("EMP002", "Casual Leave", 10),
                ("EMP002", "Sick Leave", 5),
                ("EMP003", "Casual Leave", 7),
                ("EMP003", "Sick Leave", 6),
            ]

            conn.executemany(
                """
                INSERT OR IGNORE INTO leave_balances
                (employee_id, leave_type, available_days)
                VALUES (?, ?, ?)
                """,
                leave_balances,
            )

            assets = [
                (
                    "AST001", "EMP001", "Laptop",
                    "Dell Latitude", "assigned"
                ),
                (
                    "AST002", "EMP002", "Laptop",
                    "HP EliteBook", "assigned"
                ),
                (
                    "AST003", "EMP003", "Laptop",
                    "Lenovo ThinkPad", "assigned"
                ),
            ]

            conn.executemany(
                """
                INSERT OR IGNORE INTO assets
                (asset_id, employee_id, asset_type,
                 asset_name, status)
                VALUES (?, ?, ?, ?, ?)
                """,
                assets,
            )

            payroll = [
                ("2026-11", "2026-11-30", "scheduled"),
                ("2026-12", "2026-12-31", "scheduled"),
            ]

            conn.executemany(
                """
                INSERT OR IGNORE INTO payroll_calendar
                (payroll_month, payment_date, status)
                VALUES (?, ?, ?)
                """,
                payroll,
            )

            # Assign all existing checklist tasks to demo employees.
            # EMP001 starts with tasks 1-5 complete.
            # EMP002 starts with tasks 1-3 complete.
            # EMP003 starts with all tasks pending.
            completed_until = {
                "EMP001": 5,
                "EMP002": 3,
                "EMP003": 0,
            }

            checklist_ids = [
                row[0] for row in conn.execute(
                    "SELECT id FROM checklist ORDER BY id"
                )
            ]

            assignments = [
                (
                    employee_id,
                    checklist_id,
                    int(checklist_id <= completed_count),
                )
                for employee_id, completed_count
                in completed_until.items()
                for checklist_id in checklist_ids
            ]

            conn.executemany(
                """
                INSERT OR IGNORE INTO checklist_assignments
                (employee_id, checklist_id, done)
                VALUES (?, ?, ?)
                """,
                assignments,
            )


if __name__ == "__main__":
    seed_demo_data()
    print("Synthetic employee seed completed successfully.")
