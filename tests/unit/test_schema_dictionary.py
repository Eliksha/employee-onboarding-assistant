"""M4: schema dictionary consistency (no database). The live PostgreSQL comparison is in test_postgres_m4.py."""
import copy

from backend.services import csv_import, db_roles, schema_dictionary as sd

TABLES = sd.tables()


def test_every_table_and_column_is_described():
    assert len(TABLES) == 12
    for name, table in TABLES.items():
        assert table["description"], name
        assert table["columns"] and all(c["description"] and c["type"] for c in table["columns"].values()), name
        assert set(table["primary_key"]) <= set(table["columns"]), name
        for unique in table["unique"]:
            assert set(unique) <= set(table["columns"]), name


def test_relationships_point_at_described_tables_and_columns():
    rels = sd.relationships()
    assert len(rels) == 11
    for rel in rels:
        target = TABLES[rel["to_table"]]
        assert set(rel["from_columns"]) <= set(TABLES[rel["from_table"]]["columns"])
        assert rel["to_columns"] == target["primary_key"] or rel["to_columns"] in target["unique"]
    assert {(r["from_table"], r["to_table"]) for r in rels} >= {
        ("leave_balances", "employees"), ("assets", "employees"), ("checklist_assignments", "employees"),
        ("checklist_assignments", "checklist"), ("tickets", "employees"), ("user_sessions", "user_accounts"),
        ("messages", "employees"), ("feedback", "messages"), ("escalations", "employees"), ("escalations", "messages")}


def test_security_metadata_matches_the_role_and_import_definitions():
    assert {n for n, t in TABLES.items() if t["row_level_security"]} == set(db_roles.RLS_TABLES)
    assert {n for n, t in TABLES.items() if t["reader_access"]} == set(db_roles.READER_TABLES)
    assert {n for n, t in TABLES.items() if t["sensitive"]} == {"user_accounts", "user_sessions"}
    assert not any(TABLES[n]["reader_access"] for n in ("user_accounts", "user_sessions", "messages"))
    assert set(db_roles.APP_PRIVILEGES) <= set(TABLES)
    for spec in csv_import.SPECS:
        table = TABLES[spec.table]
        assert table["import_file"] == spec.filename
        assert set(spec.columns) | set(spec.insert_defaults) <= set(table["columns"])
        assert tuple(spec.key) in {tuple(table["primary_key"])} | {tuple(u) for u in table["unique"]}, spec.table
    assert {n for n, t in TABLES.items() if t["import_file"]} == {s.table for s in csv_import.SPECS}


def test_diff_reports_every_kind_of_mismatch():
    actual = {name: {"columns": {c: {"type": v["type"], "nullable": v["nullable"]} for c, v in t["columns"].items()},
                     "primary_key": t["primary_key"], "unique": sorted(t["unique"]),
                     "foreign_keys": sorted(t["foreign_keys"], key=lambda f: f["columns"]),
                     "row_level_security": t["row_level_security"]} for name, t in TABLES.items()}
    assert sd.diff(TABLES, actual) == []
    changed = copy.deepcopy(actual)
    changed["employees"]["columns"]["email"]["nullable"] = True
    changed["assets"]["row_level_security"] = False
    changed["tickets"]["foreign_keys"] = []
    changed["new_table"] = {"columns": {}, "primary_key": [], "unique": [], "foreign_keys": [], "row_level_security": False}
    del changed["feedback"]
    problems = "\n".join(sd.diff(TABLES, changed))
    for fragment in ("employees.email", "assets: row_level_security", "tickets: foreign keys",
                     "new_table: in the database but not described", "feedback: described but not in the database"):
        assert fragment in problems
