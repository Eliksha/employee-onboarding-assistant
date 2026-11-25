"""Machine-readable schema dictionary for the OnboardAI PostgreSQL database (M4).

`backend/services/schema_dictionary.json` describes every table in schema `public`: purpose, columns
(PostgreSQL type, nullability, description), primary key, unique constraints, foreign keys and
relationships, plus security metadata (personal data, row-level security, reader/import access).
The security schemas `onboardai_private` / `onboardai_rls` are deliberately not described.

`introspect()` reads the live catalog (read-only) and `diff()` reports every mismatch, so tests and
`python -m scripts.schema_dictionary --check` can prove the dictionary matches the actual schema.
"""
import json
from functools import lru_cache
from pathlib import Path
from typing import Dict, List

PATH = Path(__file__).with_name("schema_dictionary.json")


@lru_cache(maxsize=1)
def load() -> dict:
    return json.loads(PATH.read_text(encoding="utf-8"))


def tables() -> Dict[str, dict]:
    return load()["tables"]


def relationships() -> List[dict]:
    """Flat list of foreign-key relationships: {from_table, from_columns, to_table, to_columns}."""
    out = []
    for name, table in tables().items():
        for fk in table.get("foreign_keys", []):
            out.append({"from_table": name, "from_columns": fk["columns"],
                        "to_table": fk["references"]["table"], "to_columns": fk["references"]["columns"]})
    return out


def _rows(conn, query, params=()):
    with conn.cursor() as cur:
        cur.execute(query, params)
        names = [d[0] for d in cur.description]
        return [dict(r) if isinstance(r, dict) else dict(zip(names, r)) for r in cur.fetchall()]


def introspect(conn) -> Dict[str, dict]:
    """Structural description of schema public from the PostgreSQL catalog (read-only)."""
    result: Dict[str, dict] = {}
    for row in _rows(conn, """SELECT c.relname AS table_name, c.relrowsecurity AS rls
            FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relkind = 'r' ORDER BY c.relname"""):
        result[row["table_name"]] = {"columns": {}, "primary_key": [], "unique": [], "foreign_keys": [],
                                     "row_level_security": bool(row["rls"])}
    for row in _rows(conn, """SELECT a.attrelid::regclass::text AS table_name, a.attname AS column_name,
            format_type(a.atttypid, a.atttypmod) AS data_type, NOT a.attnotnull AS nullable
            FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relkind = 'r' AND a.attnum > 0 AND NOT a.attisdropped
            ORDER BY a.attrelid, a.attnum"""):
        name = row["table_name"].split(".")[-1]
        if name in result:
            result[name]["columns"][row["column_name"]] = {"type": row["data_type"], "nullable": bool(row["nullable"])}
    for row in _rows(conn, """SELECT con.conrelid::regclass::text AS table_name, con.contype,
            ARRAY(SELECT a.attname FROM unnest(con.conkey) WITH ORDINALITY k(attnum, ord)
                  JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = k.attnum ORDER BY k.ord) AS cols,
            con.confrelid::regclass::text AS ref_table,
            ARRAY(SELECT a.attname FROM unnest(con.confkey) WITH ORDINALITY k(attnum, ord)
                  JOIN pg_attribute a ON a.attrelid = con.confrelid AND a.attnum = k.attnum ORDER BY k.ord) AS ref_cols,
            con.confdeltype
            FROM pg_constraint con JOIN pg_namespace n ON n.oid = con.connamespace
            WHERE n.nspname = 'public' AND con.contype IN ('p', 'u', 'f')"""):
        table = result.get(row["table_name"].split(".")[-1])
        if table is None:
            continue
        cols = list(row["cols"])
        if row["contype"] == "p":
            table["primary_key"] = cols
        elif row["contype"] == "u":
            table["unique"].append(cols)
        else:
            on_delete = {"a": "NO ACTION", "r": "RESTRICT", "c": "CASCADE", "n": "SET NULL", "d": "SET DEFAULT"}
            table["foreign_keys"].append({"columns": cols, "references": {
                "table": row["ref_table"].split(".")[-1], "columns": list(row["ref_cols"])},
                "on_delete": on_delete.get(row["confdeltype"], row["confdeltype"])})
    for table in result.values():
        table["unique"].sort()
        table["foreign_keys"].sort(key=lambda f: f["columns"])
    return result


def diff(dictionary: Dict[str, dict], actual: Dict[str, dict]) -> List[str]:
    """Every structural difference between the dictionary and the introspected schema."""
    problems = []
    for name in sorted(set(dictionary) | set(actual)):
        if name not in actual:
            problems.append(f"{name}: described but not in the database")
            continue
        if name not in dictionary:
            problems.append(f"{name}: in the database but not described")
            continue
        doc, real = dictionary[name], actual[name]
        doc_cols = {c: {"type": v["type"], "nullable": v["nullable"]} for c, v in doc["columns"].items()}
        if list(doc_cols) != list(real["columns"]):
            problems.append(f"{name}: columns {list(doc_cols)} != database {list(real['columns'])}")
        for column, spec in doc_cols.items():
            if column in real["columns"] and spec != real["columns"][column]:
                problems.append(f"{name}.{column}: {spec} != database {real['columns'][column]}")
        for key in ("primary_key", "row_level_security"):
            if doc.get(key) != real[key]:
                problems.append(f"{name}: {key} {doc.get(key)} != database {real[key]}")
        if sorted(doc.get("unique", [])) != real["unique"]:
            problems.append(f"{name}: unique {doc.get('unique', [])} != database {real['unique']}")
        doc_fks = sorted(({"columns": f["columns"], "references": f["references"], "on_delete": f["on_delete"]}
                          for f in doc.get("foreign_keys", [])), key=lambda f: f["columns"])
        if doc_fks != real["foreign_keys"]:
            problems.append(f"{name}: foreign keys {doc_fks} != database {real['foreign_keys']}")
    return problems
