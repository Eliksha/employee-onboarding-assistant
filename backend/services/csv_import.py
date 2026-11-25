"""Validated, idempotent CSV import of HR reference data (M4).

Files (all optional; UTF-8, one header row, exactly the listed columns in any order):
  employees.csv              employee_id, name, email, department, joining_date, location
  checklist.csv              id, phase, task
  payroll_calendar.csv       payroll_month, payment_date, status
  leave_balances.csv         employee_id, leave_type, available_days
  assets.csv                 asset_id, employee_id, asset_type, asset_name, status
  checklist_assignments.csv  employee_id, checklist_id

Guarantees
  * Everything is validated before anything is written (types, allowed values, required fields, header,
    duplicate keys and duplicate emails within a file, foreign keys against the file set + database).
  * One transaction: any validation or database error -> nothing is written.
  * Idempotent: rows are matched on natural keys; identical rows are reported "unchanged"; differing rows
    are updated (only the columns the import role may update); new rows are inserted. Re-running the same
    files changes nothing.
  * Never deletes. Database rows that are absent from a file are only counted ("not in file").
  * checklist_assignments is insert-only: missing assignments are created as pending; an employee's own
    progress (`done`) is never changed by an import.
On PostgreSQL the CLI (scripts/import_csv.py) connects as the dedicated `onboardai_importer` role
(migration 006), never as the application, reader or owner role.
"""
import csv
import io
import math
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_ROWS = 10_000
MAX_TEXT = 200
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


class CsvImportError(ValueError):
    """The import was refused (validation errors are collected in the report instead)."""


# ---------------------------------------------------------------- value validators
def _text(value: str, max_len: int = MAX_TEXT) -> str:
    value = value.strip()
    if not value:
        raise ValueError("is required")
    if len(value) > max_len:
        raise ValueError(f"is longer than {max_len} characters")
    if _CONTROL.search(value):
        raise ValueError("contains control characters")
    return value


def _employee_id(value: str) -> str:
    value = value.strip()
    if not re.fullmatch(r"EMP\d{3,6}", value):
        raise ValueError("must look like EMP001")
    return value


def _email(value: str) -> str:
    value = _text(value, 254)
    if not re.fullmatch(r"[^@\s,;]+@[^@\s,;]+\.[A-Za-z]{2,}", value):
        raise ValueError("is not a valid email address")
    return value


def _iso_date(value: str) -> str:
    value = value.strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("must be a valid date YYYY-MM-DD")
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise ValueError("must be a valid date YYYY-MM-DD") from exc


def _month(value: str) -> str:
    value = value.strip()
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", value):
        raise ValueError("must be YYYY-MM")
    return value


def _days(value: str) -> float:
    try:
        number = float(value.strip())
    except ValueError as exc:
        raise ValueError("must be a number") from exc
    if not math.isfinite(number) or number < 0 or number > 365:
        raise ValueError("must be between 0 and 365")
    return number


def _positive_int(value: str) -> int:
    value = value.strip()
    if not re.fullmatch(r"[1-9]\d{0,8}", value):
        raise ValueError("must be a positive whole number")
    return int(value)


def _one_of(*allowed: str) -> Callable[[str], str]:
    def check(value: str) -> str:
        value = value.strip()
        if value not in allowed:
            raise ValueError(f"must be one of: {', '.join(allowed)}")
        return value
    return check


# ---------------------------------------------------------------- table specifications (FK order)
@dataclass(frozen=True)
class TableSpec:
    table: str
    columns: Dict[str, Callable[[str], object]]
    key: Tuple[str, ...]
    update: Tuple[str, ...]                       # columns an import may change (subset of migration 006 grants)
    foreign_keys: Dict[str, Tuple[str, str]] = field(default_factory=dict)
    unique: Tuple[str, ...] = ()                  # extra single-column unique constraints
    insert_defaults: Dict[str, object] = field(default_factory=dict)  # fixed values for new rows only

    @property
    def filename(self) -> str:
        return f"{self.table}.csv"


SPECS: Tuple[TableSpec, ...] = (
    TableSpec("employees", {"employee_id": _employee_id, "name": _text, "email": _email, "department": _text,
                            "joining_date": _iso_date, "location": _text},
              key=("employee_id",), update=("name", "email", "department", "joining_date", "location"),
              unique=("email",)),
    TableSpec("checklist", {"id": _positive_int, "phase": _one_of("Day 1", "Week 1", "Month 1"), "task": _text},
              key=("id",), update=("phase", "task"), insert_defaults={"done": 0}),   # legacy global flag
    TableSpec("payroll_calendar", {"payroll_month": _month, "payment_date": _iso_date,
                                   "status": _one_of("scheduled", "processed", "paid", "cancelled")},
              key=("payroll_month",), update=("payment_date", "status")),
    TableSpec("leave_balances", {"employee_id": _employee_id, "leave_type": _text, "available_days": _days},
              key=("employee_id", "leave_type"), update=("available_days",),
              foreign_keys={"employee_id": ("employees", "employee_id")}),
    TableSpec("assets", {"asset_id": lambda v: _text(v, 40), "employee_id": _employee_id, "asset_type": _text,
                         "asset_name": _text, "status": _one_of("assigned", "returned", "in_repair", "lost")},
              key=("asset_id",), update=("employee_id", "asset_type", "asset_name", "status"),
              foreign_keys={"employee_id": ("employees", "employee_id")}),
    TableSpec("checklist_assignments", {"employee_id": _employee_id, "checklist_id": _positive_int},
              key=("employee_id", "checklist_id"), update=(),
              foreign_keys={"employee_id": ("employees", "employee_id"), "checklist_id": ("checklist", "id")}),
)
SPEC_BY_TABLE = {s.table: s for s in SPECS}


# ---------------------------------------------------------------- report
@dataclass
class TableResult:
    table: str
    provided: bool = False
    rows: int = 0
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    not_in_file: int = 0


@dataclass
class ImportReport:
    applied: bool = False
    errors: List[str] = field(default_factory=list)
    tables: Dict[str, TableResult] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict:
        return {"applied": self.applied, "ok": self.ok, "errors": self.errors,
                "tables": {k: vars(v) for k, v in self.tables.items()}}

    def render(self) -> str:
        lines = [f"{'APPLIED' if self.applied else 'DRY RUN (nothing written)'}"
                 f"{'' if self.ok else ' - REFUSED: validation failed, nothing written'}"]
        lines.append(f"{'table':<24}{'rows':>6}{'insert':>8}{'update':>8}{'same':>6}{'not in file':>13}")
        for r in self.tables.values():
            if r.provided:
                lines.append(f"{r.table:<24}{r.rows:>6}{r.inserted:>8}{r.updated:>8}{r.unchanged:>6}{r.not_in_file:>13}")
            else:
                lines.append(f"{r.table:<24}  (no file)")
        lines += [f"ERROR {e}" for e in self.errors]
        return "\n".join(lines)


# ---------------------------------------------------------------- parsing
def read_csv_files(directory: Path, report: ImportReport) -> Dict[str, List[dict]]:
    """Parse and validate every provided file (no database access)."""
    directory = Path(directory)
    if not directory.is_dir():
        raise CsvImportError(f"CSV directory not found: {directory}")
    known = {s.filename for s in SPECS}
    unknown = sorted(p.name for p in directory.glob("*.csv") if p.name not in known)
    for name in unknown:
        report.errors.append(f"{name}: unknown file (expected one of {', '.join(sorted(known))})")
    parsed: Dict[str, List[dict]] = {}
    for spec in SPECS:
        report.tables[spec.table] = TableResult(spec.table)
        path = directory / spec.filename
        if not path.is_file():
            continue
        report.tables[spec.table].provided = True
        if path.stat().st_size > MAX_FILE_BYTES:
            report.errors.append(f"{spec.filename}: larger than {MAX_FILE_BYTES // (1024 * 1024)} MB")
            continue
        try:
            text = path.read_bytes().decode("utf-8-sig")
        except UnicodeDecodeError:
            report.errors.append(f"{spec.filename}: not valid UTF-8")
            continue
        parsed[spec.table] = _parse_rows(spec, text, report)
        report.tables[spec.table].rows = len(parsed[spec.table])
    return parsed


def _parse_rows(spec: TableSpec, text: str, report: ImportReport) -> List[dict]:
    reader = csv.reader(io.StringIO(text, newline=""))
    header = next(reader, None)
    if header is None:
        report.errors.append(f"{spec.filename}: empty file")
        return []
    header = [h.strip() for h in header]
    expected = set(spec.columns)
    if len(header) != len(set(header)) or set(header) != expected:
        missing, extra = sorted(expected - set(header)), sorted(set(header) - expected)
        report.errors.append(f"{spec.filename}: header must be exactly {sorted(expected)}"
                             f"{'; missing ' + str(missing) if missing else ''}{'; unexpected ' + str(extra) if extra else ''}")
        return []
    rows, seen_keys, seen_unique = [], {}, {u: {} for u in spec.unique}
    for line_no, values in enumerate(reader, start=2):
        if not values or all(not v.strip() for v in values):
            continue
        if len(rows) >= MAX_ROWS:
            report.errors.append(f"{spec.filename}: more than {MAX_ROWS} rows")
            break
        if len(values) != len(header):
            report.errors.append(f"{spec.filename}:{line_no}: expected {len(header)} values, found {len(values)}")
            continue
        row, ok = {}, True
        for column, raw in zip(header, values):
            try:
                row[column] = spec.columns[column](raw)
            except ValueError as exc:
                report.errors.append(f"{spec.filename}:{line_no}: {column} {exc}")
                ok = False
        if not ok:
            continue
        key = tuple(row[k] for k in spec.key)
        if key in seen_keys:
            report.errors.append(f"{spec.filename}:{line_no}: duplicate key {dict(zip(spec.key, key))} "
                                 f"(first seen on line {seen_keys[key]})")
            continue
        seen_keys[key] = line_no
        for column in spec.unique:
            value = str(row[column]).lower()
            if value in seen_unique[column]:
                report.errors.append(f"{spec.filename}:{line_no}: duplicate {column} "
                                     f"(first seen on line {seen_unique[column][value]})")
                ok = False
            else:
                seen_unique[column][value] = line_no
        if ok:
            rows.append(row)
    return rows


# ---------------------------------------------------------------- database
class _Db:
    """Minimal adapter for psycopg2 (PostgreSQL) and sqlite3 connections."""

    def __init__(self, conn, postgres: bool):
        self.conn, self.postgres = conn, postgres

    def _q(self, query: str) -> str:
        return query.replace("?", "%s") if self.postgres else query

    def rows(self, query: str, params=()) -> List[dict]:
        cur = self.conn.cursor()
        cur.execute(self._q(query), params)
        names = [d[0] for d in cur.description]
        return [dict(r) if isinstance(r, dict) else dict(zip(names, tuple(r))) for r in cur.fetchall()]

    def execute(self, query: str, params=()) -> None:
        cur = self.conn.cursor()
        cur.execute(self._q(query), params)


_IDENT_RE = re.compile(r"[a-z_][a-z0-9_]{0,62}")


def _ident(name: str) -> str:
    """Quoted SQL identifier; only names from SPECS that also exist in the schema dictionary are allowed."""
    from backend.services import schema_dictionary

    tables = schema_dictionary.tables()
    known = set(tables) | {c for t in tables.values() for c in t["columns"]}
    if not _IDENT_RE.fullmatch(name) or name not in known:
        raise CsvImportError(f"unexpected identifier {name!r}")
    return '"' + name + '"'


def _select_sql(table: str, columns) -> str:
    return "SELECT " + ", ".join(map(_ident, columns)) + " FROM " + _ident(table)


def _insert_sql(table: str, columns) -> str:
    return ("INSERT INTO " + _ident(table) + " (" + ", ".join(map(_ident, columns)) + ") VALUES ("
            + ", ".join("?" for _ in columns) + ")")


def _update_sql(table: str, columns, key) -> str:
    return ("UPDATE " + _ident(table) + " SET " + ", ".join(_ident(c) + " = ?" for c in columns)
            + " WHERE " + " AND ".join(_ident(k) + " = ?" for k in key))


def _same(a, b) -> bool:
    if isinstance(a, float) or isinstance(b, float):
        try:
            return math.isclose(float(a), float(b), abs_tol=1e-9)
        except (TypeError, ValueError):
            return False
    return str(a) == str(b)


def run_import(conn, directory, *, apply: bool = False, postgres: bool = True) -> ImportReport:
    """Validate the CSV directory against the database and (optionally) apply it in the caller's transaction.

    The caller owns the connection and must commit only when the report says applied and ok
    (scripts/import_csv.py does this); on any error the caller rolls back.
    """
    report = ImportReport()
    parsed = read_csv_files(Path(directory), report)
    db = _Db(conn, postgres)

    existing: Dict[str, Dict[tuple, dict]] = {}
    for spec in SPECS:
        columns = list(dict.fromkeys(list(spec.key) + list(spec.update) + list(spec.unique)))
        existing[spec.table] = {tuple(r[k] for k in spec.key): r
                                for r in db.rows(_select_sql(spec.table, columns))}

    # Foreign keys and cross-row uniqueness against the union of file rows and database rows.
    for spec in SPECS:
        for row in parsed.get(spec.table, []):
            for column, (ref_table, ref_column) in spec.foreign_keys.items():
                ref_keys = {k[0] for k in existing[ref_table]} | {r[ref_column] for r in parsed.get(ref_table, [])}
                if row[column] not in ref_keys:
                    report.errors.append(f"{spec.filename}: {column} {row[column]!r} does not exist in {ref_table}")
        for column in spec.unique:
            owners = {str(r[column]).lower(): k for k, r in existing[spec.table].items()}
            for row in parsed.get(spec.table, []):
                key = tuple(row[k] for k in spec.key)
                owner = owners.get(str(row[column]).lower())
                if owner is not None and owner != key:
                    report.errors.append(f"{spec.filename}: {column} {row[column]!r} already belongs to "
                                         f"{dict(zip(spec.key, owner))}")

    plans: Dict[str, Tuple[List[dict], List[dict]]] = {}
    for spec in SPECS:
        if spec.table not in parsed:
            continue
        result, inserts, updates = report.tables[spec.table], [], []
        file_keys = set()
        for row in parsed[spec.table]:
            key = tuple(row[k] for k in spec.key)
            file_keys.add(key)
            current = existing[spec.table].get(key)
            if current is None:
                inserts.append(row)
            elif any(not _same(row[c], current[c]) for c in spec.update):
                updates.append(row)
            else:
                result.unchanged += 1
        result.inserted, result.updated = len(inserts), len(updates)
        result.not_in_file = len(set(existing[spec.table]) - file_keys)
        plans[spec.table] = (inserts, updates)

    if report.errors or not apply:
        return report

    for spec in SPECS:
        inserts, updates = plans.get(spec.table, ([], []))
        for row in inserts:
            values = {**{c: row[c] for c in spec.columns}, **spec.insert_defaults}
            db.execute(_insert_sql(spec.table, list(values)), list(values.values()))
        for row in updates:
            db.execute(_update_sql(spec.table, spec.update, spec.key),
                       [row[c] for c in spec.update] + [row[k] for k in spec.key])
    report.applied = True
    return report
