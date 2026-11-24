"""Shared PostgreSQL connection utilities for OnboardAI.

Two kinds of connection:

* `postgres_connection()` - the application's read-write connection (PG_USER). Commits on success,
  rolls back on error, and carries a server-side `statement_timeout` (PG_STATEMENT_TIMEOUT_MS).
* `postgres_readonly_connection()` - SQL-agent / read-only data access (PG_READER_USER when
  configured, else PG_USER). Every transaction is READ ONLY, has its own statement timeout and is
  always rolled back, never committed. With the dedicated reader role, the employee scope is SIGNED
  (HMAC, bound to this connection, short expiry - see employee_scope.py) and verified by row-level
  security inside the database, so changing a session variable cannot widen it.

Transport security: PG_SSLMODE / PG_SSLROOTCERT are passed to libpq. APP_ENV=production refuses to
start unless PG_SSLMODE=verify-full (certificate chain and host name verified); see validate_tls_settings.

Pooling (PG_POOL_ENABLED, default on): a small bounded pool per credential set. A lease waits at most
PG_POOL_TIMEOUT_SECONDS for a free slot (then PoolExhausted -> HTTP 503). Idle connections are validated
(`SELECT 1`) before reuse when idle longer than PG_POOL_VALIDATE_IDLE_SECONDS, recycled after
PG_POOL_MAX_LIFETIME_SECONDS, discarded after any connection-level error (database restart, network
failure, statement timeout) and reset when returned: ROLLBACK, then DISCARD ALL. The signed employee
scope is transaction-local (set_config(..., true)) and is already gone after the rollback; DISCARD ALL
additionally resets every session setting, so no request can inherit another request's scope or state.
"""

import os
import threading
import time
from collections import deque
from contextlib import contextmanager
from typing import Optional

import psycopg2
from psycopg2.extras import RealDictCursor

from backend.config import settings
from backend.services import employee_scope

SSL_MODES = ("disable", "allow", "prefer", "require", "verify-ca", "verify-full")
PRODUCTION_SSL_MODE = "verify-full"


class PoolExhausted(RuntimeError):
    """No pooled connection became free within PG_POOL_TIMEOUT_SECONDS."""


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


# ---------------------------------------------------------------- TLS
def tls_problems() -> list[str]:
    """Problems with the database TLS settings for the current APP_ENV (empty list = acceptable)."""
    mode = settings.pg_sslmode.strip().lower()
    problems = []
    if mode not in SSL_MODES:
        problems.append(f"PG_SSLMODE must be one of {', '.join(SSL_MODES)}")
    elif settings.app_env.strip().lower() == "production" and mode != PRODUCTION_SSL_MODE:
        problems.append("APP_ENV=production requires PG_SSLMODE=verify-full (certificate and host name verification)")
    root = settings.pg_sslrootcert.strip()
    if mode in ("verify-ca", "verify-full") and root and root != "system" and not os.path.isfile(root):
        problems.append("PG_SSLROOTCERT does not point to a readable CA bundle")
    return problems


def validate_tls_settings() -> None:
    """Fail closed at startup on unsafe or invalid database TLS settings (no values are echoed)."""
    problems = tls_problems()
    if problems:
        raise RuntimeError("Unsafe database TLS configuration: " + "; ".join(problems) + ".")


def _connect_kwargs(user: str, password: str, connect_timeout: int, options: Optional[str]) -> dict:
    kwargs = dict(host=settings.pg_host, port=settings.pg_port, dbname=settings.pg_database, user=user,
                  password=password, connect_timeout=connect_timeout, cursor_factory=RealDictCursor,
                  options=options, sslmode=settings.pg_sslmode.strip().lower() or "prefer")
    if settings.pg_sslrootcert.strip():
        kwargs["sslrootcert"] = settings.pg_sslrootcert.strip()
    return kwargs


# ---------------------------------------------------------------- pool
def _is_connection_error(exc: BaseException) -> bool:
    """Errors after which a connection is not reused (statement timeouts included: conservative)."""
    return isinstance(exc, (psycopg2.OperationalError, psycopg2.InterfaceError))


class _Lease:
    __slots__ = ("conn", "created")

    def __init__(self, conn, created: float):
        self.conn, self.created = conn, created


class ConnectionPool:
    """Bounded, thread-safe pool of psycopg2 connections sharing one set of connection parameters."""

    def __init__(self, kwargs: dict, max_size: int):
        self._kwargs = kwargs
        self.max_size = max(1, int(max_size))
        self._slots = threading.BoundedSemaphore(self.max_size)
        self._idle: deque = deque()          # (conn, created, returned_at); most recently returned on the right
        self._lock = threading.Lock()
        self.closed = False

    def _new(self) -> _Lease:
        return _Lease(psycopg2.connect(**self._kwargs), time.monotonic())

    @staticmethod
    def _close(conn) -> None:
        try:
            conn.close()
        except Exception:
            pass

    @staticmethod
    def _usable(conn, created: float, returned_at: float) -> bool:
        now = time.monotonic()
        if conn.closed or now - created > max(1, settings.pg_pool_max_lifetime_seconds):
            return False
        if now - returned_at < max(0.0, float(settings.pg_pool_validate_idle_seconds)):
            return True
        try:  # pre-ping: detects connections killed by a database restart or a network failure
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            conn.rollback()
            return True
        except Exception:
            return False

    def acquire(self) -> _Lease:
        if not self._slots.acquire(timeout=max(0.1, float(settings.pg_pool_timeout_seconds))):
            raise PoolExhausted("no database connection became available in time")
        try:
            while True:
                with self._lock:
                    item = self._idle.pop() if self._idle else None
                if item is None:
                    return self._new()
                conn, created, returned_at = item
                if self._usable(conn, created, returned_at):
                    return _Lease(conn, created)
                self._close(conn)
        except BaseException:
            self._slots.release()
            raise

    def release(self, lease: _Lease, discard: bool = False) -> None:
        conn = lease.conn
        try:
            if discard or self.closed or conn.closed:
                self._close(conn)
                return
            try:
                conn.rollback()
                conn.readonly = None               # client-side transaction defaults back to the server's
                conn.autocommit = True
                with conn.cursor() as cur:
                    cur.execute("DISCARD ALL")     # session settings, prepared statements, temporary tables
                conn.autocommit = False
            except Exception:
                self._close(conn)
                return
            with self._lock:
                self._idle.append((conn, lease.created, time.monotonic()))
        finally:
            self._slots.release()

    def idle_count(self) -> int:
        with self._lock:
            return len(self._idle)

    def close(self) -> None:
        self.closed = True
        with self._lock:
            idle, self._idle = list(self._idle), deque()
        for conn, _, _ in idle:
            self._close(conn)


_pools: dict = {}
_pools_lock = threading.Lock()


def _pool_for(kwargs: dict) -> ConnectionPool:
    key = tuple(sorted((k, v) for k, v in kwargs.items() if k != "cursor_factory"))
    with _pools_lock:
        pool = _pools.get(key)
        if pool is None:
            pool = _pools[key] = ConnectionPool(kwargs, settings.pg_pool_max_size)
        return pool


def close_all_pools() -> None:
    """Close every pooled connection (application shutdown, tests)."""
    with _pools_lock:
        pools = list(_pools.values())
        _pools.clear()
    for pool in pools:
        pool.close()


@contextmanager
def _leased(kwargs: dict, pooled: Optional[bool]):
    """Yield a connection: pooled (bounded, reset on return) or a fresh one that is closed afterwards."""
    if not (settings.pg_pool_enabled if pooled is None else pooled):
        conn = psycopg2.connect(**kwargs)
        try:
            yield conn
        finally:
            conn.close()
        return
    pool = _pool_for(kwargs)
    lease = pool.acquire()
    discard = False
    try:
        yield lease.conn
    except BaseException as exc:
        discard = _is_connection_error(exc)
        raise
    finally:
        pool.release(lease, discard=discard)


# ---------------------------------------------------------------- connections
@contextmanager
def postgres_connection(connect_timeout: int = 10, *, statement_timeout_ms: Optional[int] = None,
                        pooled: Optional[bool] = None):
    """Provide the application's PostgreSQL connection with commit and rollback."""

    timeout_ms = settings.pg_statement_timeout_ms if statement_timeout_ms is None else statement_timeout_ms
    options = _options(*((("statement_timeout", timeout_ms),) if timeout_ms and timeout_ms > 0 else ()))
    with _leased(_connect_kwargs(settings.pg_user, _app_password(), connect_timeout, options), pooled) as connection:
        try:
            yield connection
            connection.commit()
        except Exception:
            try:
                connection.rollback()
            except Exception:
                pass
            raise


@contextmanager
def postgres_readonly_connection(scope_employee_id: Optional[str] = None, connect_timeout: int = 10,
                                 *, pooled: Optional[bool] = None):
    """Read-only, time-limited, employee-scoped connection. Never commits."""

    user, password, dedicated = reader_credentials()
    timeout_ms = max(1, int(settings.sql_agent_statement_timeout_ms))
    options = _options(
        ("default_transaction_read_only", "on"),
        ("statement_timeout", timeout_ms),
        ("idle_in_transaction_session_timeout", max(timeout_ms * 2, 10000)),
    )
    with _leased(_connect_kwargs(user, password, connect_timeout, options), pooled) as connection:
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
                connection.rollback()  # never committed; the transaction-local signed scope ends here
            except Exception:
                pass


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
