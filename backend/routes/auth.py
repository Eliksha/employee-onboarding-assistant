"""Login, logout and current-session endpoints."""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from backend.config import settings
from backend.security import client_ip, cookie_secure, csrf_protected, current_session
from backend.services import auth, employee_db

router = APIRouter(prefix="/auth", tags=["Authentication"])
logger = logging.getLogger("app")

INVALID_CREDENTIALS = "Invalid email or password."
TOO_MANY_ATTEMPTS = "Too many failed sign-in attempts. Please wait and try again."


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=auth.MAX_PASSWORD_LENGTH)


def _user_payload(user: auth.AuthUser) -> dict:
    name = None
    if user.employee_id:
        employee = employee_db.get_employee(user.employee_id)
        name = employee["name"] if employee else None
    return {"email": user.email, "role": user.role, "employee_id": user.employee_id, "name": name}


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


@router.post("/login")
def login(body: LoginRequest, request: Request, response: Response):
    # JSON only: a cross-site HTML form cannot submit this content type (login-CSRF hardening).
    if not request.headers.get("content-type", "").lower().startswith("application/json"):
        raise HTTPException(status_code=415, detail="Content-Type must be application/json.")
    email = auth.normalize_email(body.email)
    ip = client_ip(request)
    retry_after = auth.login_limiter.retry_after(email, ip)
    if retry_after:
        logger.warning("login rate-limited account=%s", auth.email_fingerprint(email))
        raise HTTPException(status_code=429, detail=TOO_MANY_ATTEMPTS, headers={"Retry-After": str(retry_after)})

    user = auth.authenticate(email, body.password)
    if user is None:
        auth.login_limiter.record_failure(email, ip)
        logger.warning("login failed account=%s", auth.email_fingerprint(email))
        raise HTTPException(status_code=401, detail=INVALID_CREDENTIALS)

    auth.login_limiter.reset_email(email)
    token, csrf_token = auth.create_session(user)  # always a fresh session (prevents fixation)
    response.set_cookie(
        settings.session_cookie_name, token,
        max_age=settings.session_ttl_minutes * 60, path="/",
        httponly=True, samesite="strict", secure=cookie_secure(request),
    )
    _no_store(response)
    logger.info("login succeeded user_id=%s role=%s", user.user_id, user.role)
    return {"user": _user_payload(user), "csrf_token": csrf_token}


@router.post("/logout")
def logout(request: Request, response: Response, ctx: auth.SessionContext = Depends(current_session),
           _user: auth.AuthUser = Depends(csrf_protected)):
    auth.delete_session(ctx.token_hash)
    response.delete_cookie(settings.session_cookie_name, path="/", httponly=True, samesite="strict",
                           secure=cookie_secure(request))
    _no_store(response)
    logger.info("logout user_id=%s", ctx.user.user_id)
    return {"status": "signed_out"}


@router.get("/me")
def me(response: Response, ctx: auth.SessionContext = Depends(current_session)):
    """Current user and the session's CSRF token (lets the SPA restore state after a page refresh)."""
    _no_store(response)
    return {"user": _user_payload(ctx.user), "csrf_token": ctx.csrf_token}
