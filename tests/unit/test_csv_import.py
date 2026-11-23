"""M4: validated, idempotent CSV import (SQLite here; PostgreSQL + import role in test_postgres_m4.py)."""
import shutil
import sqlite3

import pytest

from backend.config import ROOT, settings
from backend.services import csv_import, employee_db
from scripts import import_csv

CSV_DIR = ROOT / "data" / "csv"


@pytest.fixture
def csv_dir(tmp_path):
    target = tmp_path / "csv"
    shutil.copytree(CSV_DIR, target)
    return target


def _conn():
    conn = sqlite3.connect(str(settings.db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _import(directory, apply=False):
    conn = _conn()
    try:
        report = csv_import.run_import(conn, directory, apply=apply, postgres=False)
        conn.commit() if report.applied and report.ok else conn.rollback()
        return report
    finally:
        conn.close()


def _snapshot():
    conn = _conn()
    try:
        return {t: conn.execute(f"SELECT * FROM {t} ORDER BY 1, 2").fetchall()
                for t in ("employees", "checklist", "payroll_calendar", "leave_balances", "assets",
                          "checklist_assignments")}
    finally:
        conn.close()


def _append(path, line):
    with open(path, "a", encoding="utf-8", newline="") as f:
        f.write(line + "\n")


def test_committed_csvs_match_the_seed_exactly(seeded_db):
    report = _import(CSV_DIR)
    assert report.ok, report.errors
    for result in report.tables.values():
        assert result.provided and result.inserted == result.updated == result.not_in_file == 0
        assert result.unchanged == result.rows > 0


def test_dry_run_writes_nothing(seeded_db, csv_dir):
    _append(csv_dir / "employees.csv", "EMP004,Isha Rao,isha.rao@example.com,Sales,2026-11-30,Pune")
    before = _snapshot()
    report = _import(csv_dir, apply=False)
    assert report.ok and not report.applied and report.tables["employees"].inserted == 1
    assert _snapshot() == before


def test_apply_inserts_updates_and_is_idempotent(seeded_db, csv_dir):
    _append(csv_dir / "employees.csv", "EMP004,Isha Rao,isha.rao@example.com,Sales,2026-11-30,Pune")
    _append(csv_dir / "leave_balances.csv", "EMP004,Casual Leave,8")
    _append(csv_dir / "checklist_assignments.csv", "EMP004,1")
    text = (csv_dir / "leave_balances.csv").read_text(encoding="utf-8").replace("EMP001,Sick Leave,6", "EMP001,Sick Leave,5.5")
    (csv_dir / "leave_balances.csv").write_text(text, encoding="utf-8")

    first = _import(csv_dir, apply=True)
    assert first.ok and first.applied
    assert (first.tables["employees"].inserted, first.tables["leave_balances"].inserted,
            first.tables["leave_balances"].updated, first.tables["checklist_assignments"].inserted) == (1, 1, 1, 1)
    assert employee_db.get_employee("EMP004")["department"] == "Sales"
    assert {r["leave_type"]: r["available_days"] for r in employee_db.get_leave_balances("EMP001")}["Sick Leave"] == 5.5
    assert [i["done"] for i in employee_db.get_employee_checklist("EMP004")] == [False]

    after_first = _snapshot()
    second = _import(csv_dir, apply=True)
    assert second.ok and all(r.inserted == r.updated == 0 for r in second.tables.values())
    assert _snapshot() == after_first


def test_any_invalid_row_rolls_back_every_file(seeded_db, csv_dir):
    _append(csv_dir / "employees.csv", "EMP004,Isha Rao,isha.rao@example.com,Sales,2026-11-30,Pune")
    _append(csv_dir / "leave_balances.csv", "EMP004,Casual Leave,-3")
    before = _snapshot()
    report = _import(csv_dir, apply=True)
    assert not report.ok and not report.applied
    assert any("available_days must be between 0 and 365" in e for e in report.errors)
    assert _snapshot() == before


@pytest.mark.parametrize("file, line, message", [
    ("employees.csv", "EMP001,Someone Else,x@example.com,Sales,2026-11-30,Pune", "duplicate key"),
    ("employees.csv", "EMP005,Dup Mail,aarav.sharma@example.com,Sales,2026-11-30,Pune", "duplicate email"),
    ("employees.csv", "EMP005,Bad Date,b@example.com,Sales,2026-02-30,Pune", "joining_date must be a valid date"),
    ("employees.csv", "E5,Bad Id,c@example.com,Sales,2026-11-30,Pune", "employee_id must look like EMP001"),
    ("employees.csv", "EMP005,Bad\x07Name,d@example.com,Sales,2026-11-30,Pune", "control characters"),
    ("leave_balances.csv", "EMP999,Casual Leave,5", "does not exist in employees"),
    ("assets.csv", "AST009,EMP001,Laptop,Spare,stolen", "status must be one of"),
    ("checklist_assignments.csv", "EMP001,99", "checklist_id 99 does not exist in checklist"),
    ("checklist.csv", "16,Year 1,Something", "phase must be one of"),
    ("payroll_calendar.csv", "2026-13,2026-12-31,scheduled", "payroll_month must be YYYY-MM"),
    ("employees.csv", "EMP006,Too,Few", "expected 6 values"),
])
def test_validation_errors_are_reported_and_nothing_is_written(seeded_db, csv_dir, file, line, message):
    _append(csv_dir / file, line)
    before = _snapshot()
    report = _import(csv_dir, apply=True)
    assert not report.ok and any(message in e for e in report.errors), report.errors
    assert _snapshot() == before


def test_email_already_owned_by_another_employee_is_rejected(seeded_db, tmp_path):
    d = tmp_path / "one"
    d.mkdir()
    (d / "employees.csv").write_text("employee_id,name,email,department,joining_date,location\n"
                                     "EMP002,Meera Iyer,aarav.sharma@example.com,Human Resources,2026-11-09,Bengaluru\n",
                                     encoding="utf-8")
    report = _import(d, apply=True)
    assert any("already belongs to" in e for e in report.errors)


@pytest.mark.parametrize("header", ["employee_id,name,email,department,joining_date",
                                    "employee_id,name,email,department,joining_date,location,salary",
                                    "employee_id,name,name,department,joining_date,location"])
def test_header_must_match_exactly(seeded_db, tmp_path, header):
    d = tmp_path / "h"
    d.mkdir()
    (d / "employees.csv").write_text(header + "\n", encoding="utf-8")
    assert any("header must be exactly" in e for e in _import(d).errors)


def test_unknown_files_and_bad_encoding_are_refused(seeded_db, tmp_path):
    d = tmp_path / "u"
    d.mkdir()
    (d / "salaries.csv").write_text("employee_id,salary\n", encoding="utf-8")
    (d / "employees.csv").write_bytes(b"employee_id,name\n\xff\xfe\n")
    errors = _import(d).errors
    assert any("salaries.csv: unknown file" in e for e in errors) and any("not valid UTF-8" in e for e in errors)


def test_import_never_changes_onboarding_progress_or_deletes(seeded_db, tmp_path):
    before_done = [i["done"] for i in employee_db.get_employee_checklist("EMP001")]
    d = tmp_path / "partial"
    d.mkdir()
    (d / "checklist_assignments.csv").write_text("employee_id,checklist_id\nEMP001,1\nEMP001,2\n", encoding="utf-8")
    (d / "leave_balances.csv").write_text("employee_id,leave_type,available_days\nEMP001,Casual Leave,8\n",
                                          encoding="utf-8")
    report = _import(d, apply=True)
    assert report.ok
    assert report.tables["checklist_assignments"].unchanged == 2 and report.tables["checklist_assignments"].not_in_file == 43
    assert report.tables["leave_balances"].not_in_file == 5
    assert [i["done"] for i in employee_db.get_employee_checklist("EMP001")] == before_done
    assert len(employee_db.get_leave_balances("EMP002")) == 2


def test_cli_dry_run_and_validation_exit_codes(seeded_db, csv_dir, capsys, tmp_path):
    assert import_csv.main([str(csv_dir)]) == 0
    assert "DRY RUN" in capsys.readouterr().out
    _append(csv_dir / "assets.csv", "AST009,EMP001,Laptop,Spare,unknown")
    out_json = tmp_path / "report.json"
    assert import_csv.main([str(csv_dir), "--apply", "--json", str(out_json)]) == 1
    assert '"ok": false' in out_json.read_text(encoding="utf-8")


def test_cli_refuses_application_and_reader_roles_on_postgres(monkeypatch, capsys):
    monkeypatch.setattr(settings, "db_backend", "postgresql")
    monkeypatch.setenv("ONBOARDAI_IMPORT_DB_PASSWORD", "x" * 20)
    for user in ("onboardai_app", "onboardai_reader"):
        monkeypatch.setenv("ONBOARDAI_IMPORT_DB_USER", user)
        assert import_csv.main(["data/csv"]) == 2
        assert "use the dedicated import role" in capsys.readouterr().out
    monkeypatch.delenv("ONBOARDAI_IMPORT_DB_PASSWORD")
    monkeypatch.delenv("ONBOARDAI_IMPORT_DB_USER")
    assert import_csv.main(["data/csv"]) == 2


def test_import_specs_stay_within_the_import_role_grants():
    from backend.services import db_roles

    for spec in csv_import.SPECS:
        grants = dict(db_roles.IMPORT_PRIVILEGES[spec.table])
        assert "INSERT" in grants and "SELECT" in grants
        assert set(spec.update) <= set(grants.get("UPDATE") or ()), spec.table
    assert "UPDATE" not in dict(db_roles.IMPORT_PRIVILEGES["checklist_assignments"])
    assert set(db_roles.IMPORT_PRIVILEGES) == {s.table for s in csv_import.SPECS}


@pytest.mark.parametrize("name", ["employees; DROP TABLE x", "user_password", "Employees", "employees--", ""])
def test_sql_identifiers_must_be_known_schema_names(name):
    with pytest.raises(csv_import.CsvImportError):
        csv_import._ident(name)
    assert csv_import._ident("leave_balances") == '"leave_balances"'
