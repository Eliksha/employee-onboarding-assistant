"""Signed employee scope for PostgreSQL row-level security (reader role).

Changing a session variable is not enough to impersonate another employee. Row-level security
calls `onboardai_rls.current_employee()`, a SECURITY DEFINER function that returns the employee
only when an HMAC-SHA256 signature over

    v1:<employee_id>:<connection_id>:<expires_epoch>

verifies against a key stored in `onboardai_private.scope_key`. Neither the reader nor the
application role can read that table or its schema. `connection_id` is the session's
`pg_backend_pid()` plus its `backend_start` timestamp, so a signature seen elsewhere (for example in
`pg_stat_activity`) cannot be replayed from another connection. It also expires after a short time.

The backend holds the same secret (PG_SCOPE_SECRET) and signs the scope after asking the server
for its connection id. The database stores only the HMAC inner/outer padded keys, so
`sha256(k_opad || sha256(k_ipad || message))` in SQL equals Python's `hmac.new(key, message, sha256)`.
"""
import hashlib
import hmac
import re

SCOPE_VERSION = "v1"
SETTING_EMPLOYEE = "app.current_employee"
SETTING_EXPIRES = "app.scope_expires"
SETTING_SIGNATURE = "app.scope_sig"
SCOPE_TTL_SECONDS = 60
MAX_SCOPE_TTL_SECONDS = 600       # the database rejects signatures valid for longer than this
MIN_SECRET_LENGTH = 32
EMPLOYEE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_BLOCK_SIZE = 64                  # SHA-256 block size in bytes


class ScopeError(ValueError):
    """Invalid employee id or missing/weak scope secret."""


def validate_employee_id(employee_id: str) -> str:
    if not isinstance(employee_id, str) or not EMPLOYEE_ID_RE.match(employee_id):
        raise ScopeError("Invalid employee id for scope")
    return employee_id


def derive_key(secret: str) -> bytes:
    """32-byte HMAC key derived from the configured secret (domain-separated)."""
    if not isinstance(secret, str) or len(secret) < MIN_SECRET_LENGTH:
        raise ScopeError(f"The scope secret must be at least {MIN_SECRET_LENGTH} characters")
    return hashlib.sha256(b"onboardai-employee-scope-v1:" + secret.encode("utf-8")).digest()


def hmac_pads(secret: str) -> tuple[bytes, bytes]:
    """(k_ipad, k_opad) as stored in onboardai_private.scope_key."""
    key = derive_key(secret).ljust(_BLOCK_SIZE, b"\0")
    return bytes(b ^ 0x36 for b in key), bytes(b ^ 0x5C for b in key)


def message(employee_id: str, connection_id: str, expires: int) -> bytes:
    return f"{SCOPE_VERSION}:{employee_id}:{connection_id}:{int(expires)}".encode("utf-8")


def sign(secret: str, employee_id: str, connection_id: str, expires: int) -> str:
    validate_employee_id(employee_id)
    return hmac.new(derive_key(secret), message(employee_id, connection_id, expires), hashlib.sha256).hexdigest()


# SQL objects created by migration 005 (owned by the table owner / administrator).
CONNECTION_ID_SQL = """
CREATE OR REPLACE FUNCTION onboardai_rls.connection_id() RETURNS text
LANGUAGE sql STABLE PARALLEL RESTRICTED SECURITY INVOKER
SET search_path = pg_catalog, pg_temp
AS $fn$
    SELECT pg_backend_pid()::text || ':' || (extract(epoch FROM a.backend_start) * 1000000)::bigint::text
    FROM pg_stat_activity AS a
    WHERE a.pid = pg_backend_pid()
$fn$
"""

CURRENT_EMPLOYEE_SQL = """
CREATE OR REPLACE FUNCTION onboardai_rls.current_employee() RETURNS text
LANGUAGE plpgsql STABLE PARALLEL RESTRICTED SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
    emp text := current_setting('app.current_employee', true);
    exp text := current_setting('app.scope_expires', true);
    sig text := current_setting('app.scope_sig', true);
    now_epoch bigint := extract(epoch FROM clock_timestamp())::bigint;
    conn text;
    k_i bytea;
    k_o bytea;
BEGIN
    IF emp IS NULL OR exp IS NULL OR sig IS NULL
       OR emp !~ '^[A-Za-z0-9_-]{1,64}$' OR exp !~ '^[0-9]{1,12}$' OR sig !~ '^[0-9a-f]{64}$' THEN
        RETURN NULL;
    END IF;
    IF exp::bigint < now_epoch OR exp::bigint > now_epoch + %(max_ttl)s THEN
        RETURN NULL;
    END IF;
    conn := onboardai_rls.connection_id();
    SELECT k.k_ipad, k.k_opad INTO k_i, k_o FROM onboardai_private.scope_key AS k WHERE k.id = 1;
    IF conn IS NULL OR k_i IS NULL OR k_o IS NULL THEN
        RETURN NULL;
    END IF;
    IF encode(sha256(k_o || sha256(k_i || convert_to('v1:' || emp || ':' || conn || ':' || exp, 'UTF8'))), 'hex')
       <> sig THEN
        RETURN NULL;
    END IF;
    RETURN emp;
END
$fn$
""".replace("%(max_ttl)s", str(MAX_SCOPE_TTL_SECONDS))

# Row-level security expression for the reader role (uncorrelated subquery -> evaluated once per query).
READER_POLICY_EXPRESSION = "employee_id = (SELECT onboardai_rls.current_employee())"
