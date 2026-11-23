"""Shared PostgreSQL connection utilities for OnboardAI.

Two kinds of connection:

* `postgres_connection()` - the application's read-write connection (PG_USER). Commits on success,
  rolls back on error, and carries a server-side `statement_timeout` (PG_STATEMENT_TIMEOUT_MS).
* `postgres_readonly_connection()` - SQL-agent / read-only data access (PG_READER_USER when
  configured, else PG_USER). Every transaction is READ ONLY, has its own statement timeout and is
  always rolled back, never committed. With the dedicated reader role, the employee scope is SIGNED
  (HMAC, bound to this connection, short expiry - see employee_scope.py) and verified by row-level
  security inside the database, so changing a session variable cannot widen it.
"""

import os
import time
from contextlib import contextmanager
from typing import Optional

import psycopg2
from psycopg2.extras import RealDictCursor

from backend.config import settings
from backend.services import employee_scope


def _options(*pairs: tuple) -> Optional[str]:
    """libpq `options` string (`-c name=value ...`); None when there is nothing to set."""
    return " ".join(f"-c {name}={value}" for name, value in pairs) or None


def _app_password() -> str:
    return settings.pg_password or os.environ.get("PGPASSWORD", "")


def reader_credentials() -> tuple[str, str, bool]:
    """(user, password, dedicated) for read-only access; falls back to the application credentials."""
    if settings.pg_reader_user.strip():
        return settings.pg_reader_user.strip(), settings.pg_reader_password, True
    return settings.pg_user, _app_password(), False


@contextmanager
def postgres_connection(connect_timeout: int = 10, *, statement_timeout_ms: Optional[int] = None):
    """Provide the application's PostgreSQL connection with commit and rollback."""

    timeout_ms = settings.pg_statement_timeout_ms if statement_timeout_ms is None else statement_timeout_ms
    connection = psycopg2.connect(
        host=settings.pg_host,
        port=settings.pg_port,
        dbname=settings.pg_database,
        user=settings.pg_user,
        password=_app_password(),
        connect_timeout=connect_timeout,
        cursor_factory=RealDictCursor,
        options=_options(*((("statement_timeout", timeout_ms),) if timeout_ms and timeout_ms > 0 else ())),
    )

    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


@contextmanager
def postgres_readonly_connection(scope_employee_id: Optional[str] = None, connect_timeout: int = 10):
    """Read-only, time-limited, employee-scoped connection. Never commits."""

    user, password, dedicated = reader_credentials()
    timeout_ms = max(1, int(settings.sql_agent_statement_timeout_ms))
    connection = psycopg2.connect(
        host=settings.pg_host,
        port=settings.pg_port,
        dbname=settings.pg_database,
        user=user,
        password=password,
        connect_timeout=connect_timeout,
        cursor_factory=RealDictCursor,
        options=_options(
            ("default_transaction_read_only", "on"),
            ("statement_timeout", timeout_ms),
            ("idle_in_transaction_session_timeout", max(timeout_ms * 2, 10000)),
        ),
    )
    try:
        # BEGIN READ ONLY on every transaction (in addition to the session default above).
        connection.set_session(readonly=True)
        if dedicated and scope_employee_id is not None:
            _set_signed_scope(connection, scope_employee_id)
        # Without a scope (or with the owner/app fallback credentials) row-level security shows the
        # reader no employee rows; the owner/app roles are not subject to the reader policies.
        yield connection
    finally:
        try:
            connection.rollback()  # read-only work is never committed
        finally:
            connection.close()


def _set_signed_scope(connection, employee_id: str) -> None:
    """Transaction-local, HMAC-signed employee scope bound to this server connection."""
    secret = settings.pg_scope_secret
    if not secret:
        raise employee_scope.ScopeError("PG_SCOPE_SECRET is required when PG_READER_USER is configured")
    employee_scope.validate_employee_id(employee_id)
    with connection.cursor() as cur:
        cur.execute("SELECT onboardai_rls.connection_id() AS connection_id")
        connection_id = cur.fetchone()["connection_id"]
        expires = int(time.time()) + employee_scope.SCOPE_TTL_SECONDS
        signature = employee_scope.sign(secret, employee_id, connection_id, expires)
        cur.execute(
            "SELECT set_config(%s, %s, true), set_config(%s, %s, true), set_config(%s, %s, true)",
            (employee_scope.SETTING_EMPLOYEE, employee_id,
             employee_scope.SETTING_EXPIRES, str(expires),
             employee_scope.SETTING_SIGNATURE, signature),
        )


def check_postgres_connection() -> bool:
    """Verify PostgreSQL connectivity."""

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 AS connected")
            return cursor.fetchone()["connected"] == 1
