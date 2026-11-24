"""FastAPI dependencies for authentication (401), CSRF and authorization (403).

Identity is always taken from the server-side session, never from URL/query/body employee IDs.
"""
import hmac

from fastapi import Depends, HTTPException, Request

from backend.config import settings
from backend.services import auth

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
CSRF_HEADER = "X-CSRF-Token"

NOT_AUTHENTICATED = "Authentication required. Please sign in."
CSRF_FAILED = "Missing or invalid CSRF token."
FORBIDDEN_OTHER_EMPLOYEE = "You can only access your own records."
FORBIDDEN_NO_WORKSPACE = "This account is not linked to an employee workspace."
FORBIDDEN_ADMIN_ONLY = "Administrator role required."


def _strip_port(value: str) -> str:
    """'203.0.113.7:51234' -> '203.0.113.7', '[2001:db8::1]:443' -> '2001:db8::1'; bare IPv6 is kept as is."""
    value = value.strip()
    if value.startswith("["):
        return value[1:value.index("]")] if "]" in value else value.strip("[]")
    if value.count(":") == 1:
        return value.split(":", 1)[0]
    return value


def client_ip(request: Request) -> str:
    """Client address. X-Forwarded-For is honoured only behind trusted proxies (TRUST_PROXY_HEADERS).

    Each of TRUSTED_PROXY_HOPS proxies appends one entry, so the client is the entry that many positions from
    the right; anything further left was supplied by the client and is ignored. Ports (as added by Azure App
    Service) are removed.
    """
    if settings.trust_proxy_headers:
        parts = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
        if parts:
            hops = max(1, int(settings.trusted_proxy_hops))
            return _strip_port(parts[-hops] if len(parts) >= hops else parts[0])
    return request.client.host if request.client else "unknown"


def is_https(request: Request) -> bool:
    if request.url.scheme == "https":
        return True
    return settings.trust_proxy_headers and request.headers.get("x-forwarded-proto", "").lower() == "https"


def cookie_secure(request: Request) -> bool:
    mode = settings.session_cookie_secure.strip().lower()
    if mode in ("true", "1", "yes"):
        return True
    if mode in ("false", "0", "no"):
        return False
    return is_https(request)


def current_session(request: Request) -> auth.SessionContext:
    ctx = auth.resolve_session(request.cookies.get(settings.session_cookie_name, ""))
    if ctx is None:
        raise HTTPException(status_code=401, detail=NOT_AUTHENTICATED)
    return ctx


def current_user(ctx: auth.SessionContext = Depends(current_session)) -> auth.AuthUser:
    return ctx.user


def csrf_protected(request: Request, ctx: auth.SessionContext = Depends(current_session)) -> auth.AuthUser:
    """Authenticated user whose state-changing request carries the session's CSRF token."""
    if request.method.upper() in UNSAFE_METHODS:
        supplied = request.headers.get(CSRF_HEADER, "")
        if not supplied or not hmac.compare_digest(supplied.encode(), ctx.csrf_token.encode()):
            raise HTTPException(status_code=403, detail=CSRF_FAILED)
    return ctx.user


FORBIDDEN_HR_ONLY = "HR/IT support role required."


def require_hr(user: auth.AuthUser = Depends(current_user)) -> auth.AuthUser:
    """HR/IT support staff only (escalation queue). Administrators and employees are refused."""
    if user.role != "hr":
        raise HTTPException(status_code=403, detail=FORBIDDEN_HR_ONLY)
    return user


def require_hr_write(user: auth.AuthUser = Depends(csrf_protected)) -> auth.AuthUser:
    if user.role != "hr":
        raise HTTPException(status_code=403, detail=FORBIDDEN_HR_ONLY)
    return user


def require_admin(user: auth.AuthUser = Depends(current_user)) -> auth.AuthUser:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail=FORBIDDEN_ADMIN_ONLY)
    return user


def require_admin_write(user: auth.AuthUser = Depends(csrf_protected)) -> auth.AuthUser:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail=FORBIDDEN_ADMIN_ONLY)
    return user


def assert_own_employee(user: auth.AuthUser, employee_id: str | None) -> str:
    """Return the session's employee ID; 403 if the account has none or a different ID was requested."""
    if user.employee_id is None:
        raise HTTPException(status_code=403, detail=FORBIDDEN_NO_WORKSPACE)
    if employee_id is not None and employee_id != user.employee_id:
        raise HTTPException(status_code=403, detail=FORBIDDEN_OTHER_EMPLOYEE)
    return user.employee_id


def own_employee_read(employee_id: str, user: auth.AuthUser = Depends(current_user)) -> str:
    """Path-parameter guard for GET /employees/{employee_id}/..."""
    return assert_own_employee(user, employee_id)


def own_employee_write(employee_id: str, user: auth.AuthUser = Depends(csrf_protected)) -> str:
    """Path-parameter guard for state-changing /employees/{employee_id}/... requests (CSRF checked first)."""
    return assert_own_employee(user, employee_id)
