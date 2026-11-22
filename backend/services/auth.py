"""Email/password authentication: Argon2 hashing, server-side sessions, login rate limiting.

Security properties
* Passwords are stored only as Argon2id hashes (argon2-cffi defaults); plaintext is never stored or logged.
* Unknown emails are verified against a dummy hash so response time does not reveal account existence.
* Session identifiers are 256-bit random tokens; only their SHA-256 hash is stored server-side.
* Sessions have an absolute lifetime and an idle timeout; logout deletes the server-side record.
* Each session carries its own random CSRF token, required on state-changing requests.
"""
import hashlib
import secrets
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, Optional, Tuple

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from backend.config import settings
from backend.services import db

ROLES = ("employee", "admin")
MAX_PASSWORD_LENGTH = 1024
TOUCH_INTERVAL_SECONDS = 60

_hasher = PasswordHasher()
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(24))


class AccountError(ValueError):
    """Invalid account data supplied to provisioning."""


@dataclass(frozen=True)
class AuthUser:
    user_id: int
    email: str
    role: str
    employee_id: Optional[str]


@dataclass(frozen=True)
class SessionContext:
    user: AuthUser
    csrf_token: str
    token_hash: str


def _now() -> int:
    return int(time.time())


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def email_fingerprint(email: str) -> str:
    """Short, non-reversible identifier for logs (the email itself is not logged)."""
    return hashlib.sha256(normalize_email(email).encode("utf-8")).hexdigest()[:10]


def validate_password(password: str) -> None:
    if not isinstance(password, str) or len(password) < settings.password_min_length:
        raise AccountError(f"Password must be at least {settings.password_min_length} characters.")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise AccountError("Password is too long.")


# ---------------------------------------------------------------- accounts
def upsert_account(email: str, password: str, employee_id: Optional[str], role: str = "employee") -> int:
    """Create or update an account (idempotent by email). Returns the account id."""
    email = normalize_email(email)
    if "@" not in email or len(email) > 254:
        raise AccountError("A valid email address is required.")
    if role not in ROLES:
        raise AccountError(f"Role must be one of {ROLES}.")
    if role == "employee" and not employee_id:
        raise AccountError("Employee accounts must be linked to an employee ID.")
    validate_password(password)
    password_hash = _hasher.hash(password)
    now = _now()
    with db._conn() as con:
        if employee_id is not None:
            if db._execute(con, "SELECT 1 FROM employees WHERE employee_id = ?", (employee_id,), one=True) is None:
                raise AccountError(f"Unknown employee ID: {employee_id}")
            other = db._execute(con, "SELECT email FROM user_accounts WHERE employee_id = ? AND email <> ?",
                                (employee_id, email), one=True)
            if other is not None:
                raise AccountError(f"Employee {employee_id} is already linked to another account.")
        row = db._execute(con, "SELECT id FROM user_accounts WHERE email = ?", (email,), one=True)
        if row is not None:
            db._execute(con, """UPDATE user_accounts SET password_hash = ?, employee_id = ?, role = ?,
                is_active = 1, updated_at = ? WHERE id = ?""", (password_hash, employee_id, role, now, row["id"]))
            # A password/role change invalidates every existing session of the account.
            db._execute(con, "DELETE FROM user_sessions WHERE user_id = ?", (row["id"],))
            return int(row["id"])
        return int(db._insert_id(con, """INSERT INTO user_accounts
            (email, password_hash, employee_id, role, is_active, created_at, updated_at)
            VALUES (?, ?, ?, ?, 1, ?, ?)""", (email, password_hash, employee_id, role, now, now)))


def set_account_active(email: str, active: bool) -> bool:
    with db._conn() as con:
        row = db._execute(con, "SELECT id FROM user_accounts WHERE email = ?", (normalize_email(email),), one=True)
        if row is None:
            return False
        db._execute(con, "UPDATE user_accounts SET is_active = ?, updated_at = ? WHERE id = ?",
                    (int(active), _now(), row["id"]))
        if not active:
            db._execute(con, "DELETE FROM user_sessions WHERE user_id = ?", (row["id"],))
    return True


def list_accounts() -> list:
    with db._conn() as con:
        rows = db._execute(con, """SELECT email, employee_id, role, is_active FROM user_accounts
            ORDER BY role, email""", all_rows=True)
    return [dict(r) for r in rows]


def authenticate(email: str, password: str) -> Optional[AuthUser]:
    """Return the user for valid credentials, else None. Constant work for unknown emails."""
    email = normalize_email(email)
    if not isinstance(password, str) or len(password) > MAX_PASSWORD_LENGTH:
        password = ""
    with db._conn() as con:
        row = db._execute(con, """SELECT id, email, password_hash, employee_id, role, is_active
            FROM user_accounts WHERE email = ?""", (email,), one=True)
    if row is None:
        _verify(_DUMMY_HASH, password)
        return None
    if not _verify(row["password_hash"], password) or not row["is_active"]:
        return None
    if _hasher.check_needs_rehash(row["password_hash"]):
        with db._conn() as con:
            db._execute(con, "UPDATE user_accounts SET password_hash = ?, updated_at = ? WHERE id = ?",
                        (_hasher.hash(password), _now(), row["id"]))
    return AuthUser(int(row["id"]), row["email"], row["role"], row["employee_id"])


def _verify(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


# ---------------------------------------------------------------- sessions
def create_session(user: AuthUser) -> Tuple[str, str]:
    """Create a new server-side session. Returns (session_token, csrf_token)."""
    token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    now = _now()
    expires = now + settings.session_ttl_minutes * 60
    with db._conn() as con:
        # Housekeeping: drop expired sessions (cheap; keeps the table small).
        db._execute(con, "DELETE FROM user_sessions WHERE expires_at <= ? OR last_seen_at <= ?",
                    (now, now - settings.session_idle_minutes * 60))
        db._execute(con, """INSERT INTO user_sessions
            (token_hash, user_id, csrf_token, created_at, last_seen_at, expires_at) VALUES (?, ?, ?, ?, ?, ?)""",
                    (hash_token(token), user.user_id, csrf_token, now, now, expires))
    return token, csrf_token


def resolve_session(token: str) -> Optional[SessionContext]:
    """Validate a session token; expired, idle or orphaned sessions are deleted and rejected."""
    if not token or len(token) > 200:
        return None
    token_hash = hash_token(token)
    now = _now()
    with db._conn() as con:
        row = db._execute(con, """SELECT s.user_id, s.csrf_token, s.last_seen_at, s.expires_at,
                a.email, a.role, a.employee_id, a.is_active
            FROM user_sessions AS s JOIN user_accounts AS a ON a.id = s.user_id
            WHERE s.token_hash = ?""", (token_hash,), one=True)
        if row is None:
            return None
        idle_seconds = settings.session_idle_minutes * 60
        idle_limit = row["last_seen_at"] + idle_seconds
        if now >= row["expires_at"] or now >= idle_limit or not row["is_active"]:
            db._execute(con, "DELETE FROM user_sessions WHERE token_hash = ?", (token_hash,))
            return None
        # Refresh last_seen at most once a minute to limit writes, but always within half the idle
        # window, so a user who stays active is never timed out (even with short idle settings).
        if now - row["last_seen_at"] >= min(TOUCH_INTERVAL_SECONDS, max(1, idle_seconds // 2)):
            db._execute(con, "UPDATE user_sessions SET last_seen_at = ? WHERE token_hash = ?", (now, token_hash))
    user = AuthUser(int(row["user_id"]), row["email"], row["role"], row["employee_id"])
    return SessionContext(user=user, csrf_token=row["csrf_token"], token_hash=token_hash)


def delete_session(token_hash: str) -> None:
    with db._conn() as con:
        db._execute(con, "DELETE FROM user_sessions WHERE token_hash = ?", (token_hash,))


# ---------------------------------------------------------------- login rate limiting
class LoginRateLimiter:
    """Sliding-window counter of failed logins per email and per client IP (in-process)."""

    def __init__(self):
        self._failures: Dict[str, Deque[float]] = {}
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> Deque[float]:
        window = self._failures.setdefault(key, deque())
        while window and window[0] <= now - settings.login_window_seconds:
            window.popleft()
        return window

    def retry_after(self, email: str, ip: str) -> int:
        """Seconds until another attempt is allowed (0 = allowed now)."""
        now = time.time()
        waits = []
        with self._lock:
            for key, limit in ((f"email:{email}", settings.login_max_failures_per_email),
                               (f"ip:{ip}", settings.login_max_failures_per_ip)):
                window = self._prune(key, now)
                if len(window) >= limit:
                    waits.append(int(window[0] + settings.login_window_seconds - now) + 1)
        return max(waits, default=0)

    def record_failure(self, email: str, ip: str) -> None:
        now = time.time()
        with self._lock:
            for key in (f"email:{email}", f"ip:{ip}"):
                self._prune(key, now).append(now)

    def reset_email(self, email: str) -> None:
        with self._lock:
            self._failures.pop(f"email:{email}", None)

    def clear(self) -> None:
        with self._lock:
            self._failures.clear()


login_limiter = LoginRateLimiter()
