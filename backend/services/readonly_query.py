"""Read-only query execution for the SQL agent and employee data lookups.

Layers of protection (each one works even if another fails):

1. `assert_select_only` - parses the statement with PostgreSQL's own parser (pglast / libpg_query)
   and accepts exactly one plain SELECT built only from allow-listed syntax: allow-listed tables
   (the reader's tables), allow-listed functions and cast types. Everything else - SET, DO, CALL,
   data-modifying CTEs, SELECT INTO, FOR UPDATE, set-returning functions in FROM, catalog tables,
   and every function not on the list (set_config, current_setting, pg_sleep, ... in any quoting or
   Unicode-escape spelling, because the parser resolves those before the check) - is rejected.
2. Connection - PostgreSQL: `postgres_readonly_connection` (READ ONLY transaction, statement
   timeout, least-privilege reader role, HMAC-signed employee scope verified by row-level security
   inside the database, always rolled back). SQLite: `mode=ro` + `PRAGMA query_only` + a deadline.
3. Result size - at most `max_rows` rows are fetched (`SQL_AGENT_MAX_ROWS` by default). PostgreSQL
   uses a server-side cursor, so the server never streams more than `max_rows + 1` rows.

Queries must use bound parameters (`?` placeholders). The text that is validated is the text that
runs: every `?` must be a real parameter (not inside a literal) and the count must match `params`.
"""
import logging
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence

import pglast
from pglast import ast
from psycopg2 import errors as pg_errors
from psycopg2.extras import RealDictCursor

from backend.config import settings
from backend.services import postgres
from backend.services.db_roles import READER_TABLES

logger = logging.getLogger("app")

MAX_QUERY_LENGTH = 5000


class UnsafeQueryError(ValueError):
    """The statement is not a single allow-listed SELECT (rejected before reaching the database)."""


class QueryTimeoutError(RuntimeError):
    """The statement exceeded SQL_AGENT_STATEMENT_TIMEOUT_MS and was cancelled."""


class QueryPermissionError(PermissionError):
    """The database refused the statement (missing privilege or read-only transaction)."""


@dataclass
class ReadOnlyResult:
    rows: List[dict] = field(default_factory=list)
    truncated: bool = False  # True when more than max_rows rows matched


# Syntax-tree node types a read-only query may contain. Everything else is rejected.
_ALLOWED_NODES = frozenset({
    ast.RawStmt, ast.SelectStmt, ast.ResTarget, ast.ColumnRef, ast.String, ast.Integer, ast.Float,
    ast.Boolean, ast.A_Const, ast.A_Star, ast.RangeVar, ast.Alias, ast.JoinExpr, ast.A_Expr, ast.BoolExpr,
    ast.NullTest, ast.BooleanTest, ast.FuncCall, ast.SortBy, ast.ParamRef, ast.TypeCast, ast.TypeName,
    ast.SubLink, ast.RangeSubselect, ast.CommonTableExpr, ast.WithClause, ast.CaseExpr, ast.CaseWhen,
    ast.CoalesceExpr, ast.MinMaxExpr, ast.WindowDef, ast.RowExpr,
})

# Pure, side-effect-free functions (aggregates, string, numeric and date helpers).
ALLOWED_FUNCTIONS = frozenset({
    "count", "sum", "avg", "min", "max", "bool_and", "bool_or", "string_agg", "array_agg",
    "row_number", "rank", "dense_rank",
    "lower", "upper", "length", "char_length", "trim", "btrim", "ltrim", "rtrim", "substring", "position",
    "replace", "concat", "concat_ws", "left", "right", "initcap",
    "round", "floor", "ceil", "ceiling", "abs",
    "now", "date_trunc", "date_part", "extract", "to_char", "to_date", "age", "make_date",
})

ALLOWED_CAST_TYPES = frozenset({
    "int2", "int4", "int8", "smallint", "integer", "int", "bigint", "numeric", "decimal", "float4", "float8",
    "real", "text", "varchar", "bpchar", "char", "bool", "boolean", "date", "timestamp", "timestamptz",
    "interval", "time",
})


def _names(nodes) -> List[str]:
    return [n.sval for n in (nodes or ()) if isinstance(n, ast.String)]


def _qualified_allowed(names: List[str], allowed: frozenset) -> bool:
    if not names or len(names) > 2:
        return False
    if len(names) == 2 and names[0] != "pg_catalog":
        return False
    return names[-1] in allowed


def _walk(node, visit) -> None:
    if isinstance(node, ast.Node):
        visit(node)
        for slot in node.__slots__:
            _walk(getattr(node, slot, None), visit)
    elif isinstance(node, (list, tuple)):
        for item in node:
            _walk(item, visit)


def _numbered(query: str) -> tuple:
    """Replace each `?` with $1..$n (the positions the drivers bind) so PostgreSQL can parse it."""
    parts = query.split("?")
    out = parts[0]
    for i, part in enumerate(parts[1:], start=1):
        out += f"${i}" + part
    return out, len(parts) - 1


def assert_select_only(query: str, param_count: Optional[int] = None) -> str:
    """Return the statement if it is one allow-listed SELECT, else raise UnsafeQueryError."""
    if not isinstance(query, str) or not query.strip():
        raise UnsafeQueryError("Empty query")
    if len(query) > MAX_QUERY_LENGTH:
        raise UnsafeQueryError("Query too long")
    text = query.strip()
    numbered, placeholders = _numbered(text)
    try:
        statements = pglast.parse_sql(numbered)
    except pglast.parser.ParseError as exc:
        raise UnsafeQueryError("Query is not valid PostgreSQL syntax") from exc
    if len(statements) != 1:
        raise UnsafeQueryError("Exactly one statement is allowed")
    if not isinstance(statements[0].stmt, ast.SelectStmt):
        raise UnsafeQueryError(f"Only SELECT statements are allowed (got {type(statements[0].stmt).__name__})")

    cte_names = set()
    _walk(statements, lambda n: cte_names.add(n.ctename) if isinstance(n, ast.CommonTableExpr) else None)
    param_refs = []

    def visit(node):
        kind = type(node)
        if kind not in _ALLOWED_NODES:
            raise UnsafeQueryError(f"SQL construct not allowed in read-only queries: {kind.__name__}")
        if kind is ast.SelectStmt:
            if node.intoClause is not None:
                raise UnsafeQueryError("SELECT INTO is not allowed")
            if node.lockingClause:
                raise UnsafeQueryError("Row locking (FOR UPDATE/SHARE) is not allowed")
        elif kind is ast.RangeVar:
            if node.catalogname or node.schemaname not in (None, "public"):
                raise UnsafeQueryError(f"Schema not allowed in read-only queries: {node.schemaname}")
            is_cte = node.schemaname is None and node.relname in cte_names
            if node.relname not in READER_TABLES and not is_cte:
                raise UnsafeQueryError(f"Table not allowed in read-only queries: {node.relname}")
        elif kind is ast.FuncCall:
            names = _names(node.funcname)
            if not _qualified_allowed(names, ALLOWED_FUNCTIONS):
                raise UnsafeQueryError(f"Function not allowed in read-only queries: {'.'.join(names)}")
        elif kind is ast.TypeName:
            names = _names(node.names)
            if not _qualified_allowed(names, ALLOWED_CAST_TYPES):
                raise UnsafeQueryError(f"Type not allowed in read-only queries: {'.'.join(names)}")
        elif kind is ast.ParamRef:
            param_refs.append(node.number)

    _walk(statements, visit)
    if len(param_refs) != placeholders:
        raise UnsafeQueryError("Placeholders must be real parameters (not inside literals or identifiers)")
    if param_count is not None and param_count != placeholders:
        raise UnsafeQueryError(f"Expected {placeholders} parameters, got {param_count}")
    return text


def _limit(max_rows: Optional[int]) -> int:
    configured = max(1, int(settings.sql_agent_max_rows))
    return configured if max_rows is None else max(1, min(int(max_rows), configured))


def _backend_is_postgres() -> bool:
    backend = settings.db_backend.strip().lower()
    if backend not in {"sqlite", "postgresql"}:
        raise ValueError(f"Unsupported DB_BACKEND: {backend}")
    return backend == "postgresql"


@contextmanager
def sqlite_readonly_connection():
    """Read-only SQLite connection whose statements are interrupted after the agent timeout."""
    path = Path(settings.db_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Database not found: {path}")
    conn = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA query_only = ON")
        # The deadline starts here; callers run exactly one statement right away.
        deadline = time.monotonic() + max(1, int(settings.sql_agent_statement_timeout_ms)) / 1000
        conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 1000)
        yield conn
    finally:
        conn.close()


def _fetch_postgres(query: str, params: Sequence, scope: Optional[str], limit: int) -> list:
    try:
        with postgres.postgres_readonly_connection(scope_employee_id=scope) as conn:
            # Server-side cursor: DECLARE accepts only SELECT/VALUES, and FETCH returns limit + 1 rows.
            with conn.cursor(name="onboardai_readonly", cursor_factory=RealDictCursor) as cur:
                cur.itersize = limit + 1
                # Same text as validated: literal % escaped for the driver, each ? bound as a parameter.
                cur.execute(query.replace("%", "%%").replace("?", "%s"), tuple(params))
                return cur.fetchmany(limit + 1)
    except pg_errors.QueryCanceled as exc:
        raise QueryTimeoutError("Read-only query timed out") from exc
    except (pg_errors.InsufficientPrivilege, pg_errors.ReadOnlySqlTransaction) as exc:
        raise QueryPermissionError("The database refused the read-only query") from exc


def _fetch_sqlite(query: str, params: Sequence, limit: int) -> list:
    try:
        with sqlite_readonly_connection() as conn:
            return conn.execute(query, tuple(params)).fetchmany(limit + 1)
    except sqlite3.OperationalError as exc:
        message = str(exc).lower()
        if "interrupt" in message:
            raise QueryTimeoutError("Read-only query timed out") from exc
        if "readonly" in message or "read-only" in message or "query_only" in message:
            raise QueryPermissionError("The database refused the read-only query") from exc
        raise


def fetch_readonly(
    query: str,
    params: Sequence = (),
    *,
    scope_employee_id: Optional[str] = None,
    max_rows: Optional[int] = None,
) -> ReadOnlyResult:
    """Run one validated SELECT with read-only, timeout, row-limit and employee-scope protection.

    `scope_employee_id` becomes the signed row-level-security scope on PostgreSQL; the query itself
    must still filter by employee (defence in depth). `max_rows` can lower, never raise, the limit.
    """
    params = tuple(params)
    statement = assert_select_only(query, param_count=len(params))
    limit = _limit(max_rows)
    if _backend_is_postgres():
        raw = _fetch_postgres(statement, params, scope_employee_id, limit)
    else:
        raw = _fetch_sqlite(statement, params, limit)
    rows = [dict(r) for r in raw]
    truncated = len(rows) > limit
    if truncated:
        logger.warning("read-only query returned more than %d rows; result truncated", limit)
        rows = rows[:limit]
    return ReadOnlyResult(rows=rows, truncated=truncated)


def reader_is_dedicated() -> bool:
    """True when a separate least-privilege reader role is configured (PostgreSQL)."""
    return postgres.reader_credentials()[2]
