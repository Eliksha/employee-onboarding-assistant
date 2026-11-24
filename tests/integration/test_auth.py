"""Authentication, session, CSRF, rate-limiting and authorization tests (isolated SQLite, no network)."""
import re

import pytest
from argon2 import PasswordHasher
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from backend import manage_accounts
from backend.config import settings
from backend.main import app
from backend.services import auth, db, employee_db, llm, retriever
from tests.conftest import login

COOKIE = settings.session_cookie_name
HITS = [{"source": "handbook.md", "section": "3. Payroll",
         "text": "3. Payroll: Salary is credited on the last working day of every month.", "score": 0.9}]


def new_client():
    return TestClient(app, raise_server_exceptions=False)


def session_rows():
    with db._conn() as con:
        return [dict(r) for r in db._execute(con, "SELECT * FROM user_sessions", all_rows=True)]


# ---------------------------------------------------------------- 1-4 login / logout
def test_successful_login_sets_secure_session_cookie(app_client, accounts):
    r = app_client.post("/auth/login", json={"email": "  Aarav.Sharma@Example.com ", "password": accounts["emp1"].password})
    assert r.status_code == 200
    body = r.json()
    assert body["user"] == {"email": "aarav.sharma@example.com", "role": "employee", "employee_id": "EMP001", "name": "Aarav Sharma"}
    assert len(body["csrf_token"]) >= 40
    set_cookie = r.headers["set-cookie"]
    assert set_cookie.startswith(f"{COOKIE}=")
    assert "HttpOnly" in set_cookie and "SameSite=strict" in set_cookie and "Path=/" in set_cookie
    assert "Max-Age=" in set_cookie and "Secure" not in set_cookie  # plain-HTTP test server, SESSION_COOKIE_SECURE=auto
    assert r.headers["cache-control"] == "no-store"
    token = app_client.cookies.get(COOKIE)
    assert token and token not in body.values() and token != body["csrf_token"]
    # Only the SHA-256 of the session token is stored server-side.
    rows = session_rows()
    assert len(rows) == 1 and rows[0]["token_hash"] == auth.hash_token(token) and token not in str(rows)


@pytest.mark.parametrize("who", ["wrong_password", "unknown_email"])
def test_failed_login_is_generic(app_client, accounts, who):
    email = accounts["emp1"].email if who == "wrong_password" else "nobody@example.com"
    r = app_client.post("/auth/login", json={"email": email, "password": "not-the-password-123"})
    assert r.status_code == 401 and r.json() == {"detail": "Invalid email or password."}
    assert "set-cookie" not in r.headers and session_rows() == []


def test_unknown_email_still_performs_a_password_hash_check(accounts, monkeypatch):
    calls = []
    real = auth._verify
    monkeypatch.setattr(auth, "_verify", lambda h, p: calls.append(h) or real(h, p))
    assert auth.authenticate("ghost@example.com", "whatever-password") is None
    assert calls == [auth._DUMMY_HASH]  # same Argon2 work as a real account: no timing oracle


def test_login_requires_json_content_type(app_client, accounts):
    r = app_client.post("/auth/login", content=f'{{"email":"{accounts["emp1"].email}","password":"x"}}',
                        headers={"content-type": "text/plain"})
    assert r.status_code in (415, 422) and COOKIE not in app_client.cookies


def test_logout_invalidates_server_side_session(emp1_client):
    token = emp1_client.cookies.get(COOKIE)
    assert emp1_client.get("/auth/me").status_code == 200
    r = emp1_client.post("/auth/logout")
    assert r.status_code == 200 and r.json() == {"status": "signed_out"}
    assert f"{COOKIE}=" in r.headers["set-cookie"] and "Max-Age=0" in r.headers["set-cookie"]
    assert session_rows() == []
    replay = new_client()
    replay.cookies.set(COOKIE, token)  # a stolen/old cookie must not work after logout
    assert replay.get("/auth/me").status_code == 401
    assert replay.get("/employees/EMP001").status_code == 401


# ---------------------------------------------------------------- 5, 13 expiry, persistence, invalidation
def test_session_expires_after_absolute_lifetime(emp1_client, monkeypatch):
    start = auth._now()
    monkeypatch.setattr(auth, "_now", lambda: start + settings.session_ttl_minutes * 60 + 1)
    monkeypatch.setattr(settings, "session_idle_minutes", 10 ** 6)
    assert emp1_client.get("/employees/EMP001").status_code == 401
    assert session_rows() == []  # expired session deleted


def test_session_expires_after_idle_timeout(emp1_client, monkeypatch):
    start = auth._now()
    monkeypatch.setattr(auth, "_now", lambda: start + settings.session_idle_minutes * 60 + 1)
    assert emp1_client.get("/auth/me").status_code == 401


def test_activity_extends_idle_window(emp1_client, monkeypatch):
    start = auth._now()
    half = settings.session_idle_minutes * 60 // 2 + 5
    monkeypatch.setattr(auth, "_now", lambda: start + half)
    assert emp1_client.get("/auth/me").status_code == 200  # touches last_seen
    monkeypatch.setattr(auth, "_now", lambda: start + 2 * half)
    assert emp1_client.get("/auth/me").status_code == 200


def test_active_session_survives_short_idle_timeout(emp1_client, monkeypatch):
    """Regression (final Docker verification): with a 1-minute idle timeout, requests every 40 s must keep
    the session alive; previously last_seen was refreshed only every 60 s, so active users were signed out."""
    monkeypatch.setattr(settings, "session_idle_minutes", 1)
    start = auth._now()
    for offset in (40, 80, 120):
        monkeypatch.setattr(auth, "_now", lambda o=offset: start + o)
        assert emp1_client.get("/auth/me").status_code == 200, offset
    monkeypatch.setattr(auth, "_now", lambda: start + 120 + 61)  # then genuinely idle for > 60 s
    assert emp1_client.get("/auth/me").status_code == 401


def test_session_persists_across_page_refresh(emp1_client):
    csrf = emp1_client.headers["X-CSRF-Token"]
    refreshed = new_client()  # a "new page load" with only the browser cookie
    refreshed.cookies.set(COOKIE, emp1_client.cookies.get(COOKIE))
    me = refreshed.get("/auth/me")
    assert me.status_code == 200 and me.json()["user"]["employee_id"] == "EMP001"
    assert me.json()["csrf_token"] == csrf
    assert refreshed.get("/employees/EMP001").status_code == 200


def test_new_login_issues_new_session_and_password_change_revokes_sessions(app_client, accounts):
    login(app_client, accounts["emp1"])
    first = app_client.cookies.get(COOKIE)
    login(app_client, accounts["emp1"])
    second = app_client.cookies.get(COOKIE)
    assert first != second  # no session fixation
    auth.upsert_account(accounts["emp1"].email, "a-completely-new-password-42", "EMP001", "employee")
    assert app_client.get("/auth/me").status_code == 401
    assert session_rows() == []


def test_disabled_account_cannot_sign_in_and_loses_sessions(emp1_client, accounts):
    assert auth.set_account_active(accounts["emp1"].email, False)
    assert emp1_client.get("/auth/me").status_code == 401
    r = emp1_client.post("/auth/login", json={"email": accounts["emp1"].email, "password": accounts["emp1"].password})
    assert r.status_code == 401 and r.json()["detail"] == "Invalid email or password."


# ---------------------------------------------------------------- 6 unauthenticated access
def _all_api_routes():
    for item in app.router.routes:
        router = getattr(item, "original_router", None)
        routes = router.routes if router is not None else [item]
        for r in routes:
            if isinstance(r, APIRoute):
                for method in r.methods:
                    yield method, r.path


PUBLIC = {("GET", "/health"), ("GET", "/ready"), ("POST", "/auth/login")}


def test_route_inventory_is_complete():
    routes = set(_all_api_routes())
    assert len(routes) == 23 and PUBLIC <= routes


@pytest.mark.parametrize("method, path", sorted(set(_all_api_routes()) - PUBLIC))
def test_every_non_public_route_requires_authentication(app_client, method, path):
    url = path.replace("{employee_id}", "EMP001").replace("{item_id}", "1").replace("{escalation_id}", "1")
    r = app_client.request(method, url, json={})
    assert r.status_code == 401, f"{method} {path} -> {r.status_code}"
    assert r.json() == {"detail": "Authentication required. Please sign in."}


def test_forged_or_malformed_cookie_is_rejected(app_client, accounts):
    app_client.cookies.set(COOKIE, "forged-" + "x" * 40)
    assert app_client.get("/employees/EMP001").status_code == 401
    app_client.cookies.set(COOKIE, "y" * 500)
    assert app_client.get("/auth/me").status_code == 401


# ---------------------------------------------------------------- 7-8 cross-employee access
@pytest.mark.parametrize("path", ["/employees/EMP002", "/employees/EMP002/leave-balances", "/employees/EMP002/assets",
                                  "/employees/EMP002/checklist", "/employees/EMP002/tickets", "/history?employee_id=EMP002",
                                  "/employees/EMP999"])
def test_cross_employee_reads_are_forbidden(emp1_client, path):
    r = emp1_client.get(path)
    assert r.status_code == 403 and r.json() == {"detail": "You can only access your own records."}


def test_own_records_are_readable(emp1_client):
    for path in ("/employees/EMP001", "/employees/EMP001/leave-balances", "/employees/EMP001/assets",
                 "/employees/EMP001/checklist", "/employees/EMP001/tickets", "/history", "/history?employee_id=EMP001",
                 "/employees/payroll/calendar"):
        assert emp1_client.get(path).status_code == 200, path
    assert emp1_client.get("/employees/EMP001").json()["employee_id"] == "EMP001"


def test_cross_employee_writes_are_forbidden_and_change_nothing(emp1_client):
    before_checklist = employee_db.get_employee_checklist("EMP002")
    before_tickets = employee_db.get_employee_tickets("EMP002")
    assert emp1_client.patch("/employees/EMP002/checklist/1", json={"done": not before_checklist[0]["done"]}).status_code == 403
    assert emp1_client.post("/employees/EMP002/tickets",
                            json={"category": "IT", "subject": "Not mine", "description": "Cross-employee attempt"}).status_code == 403
    assert emp1_client.post("/chat", json={"question": "What is my leave balance?", "employee_id": "EMP002"}).status_code == 403
    assert employee_db.get_employee_checklist("EMP002") == before_checklist
    assert employee_db.get_employee_tickets("EMP002") == before_tickets


def test_feedback_only_on_own_messages(app_client, accounts, monkeypatch, indexed_env):
    env = indexed_env
    monkeypatch.setattr(env, "similarity_threshold", 0.0)
    monkeypatch.setattr(llm, "generate_answer", lambda q, p: "8 per year")
    with new_client() as other:
        login(other, accounts["emp2"])
        mid = other.post("/chat", json={"question": "casual leaves"}).json()["message_id"]
        assert other.post("/feedback", json={"message_id": mid, "rating": "up"}).status_code == 200
    login(app_client, accounts["emp1"])
    assert app_client.post("/feedback", json={"message_id": mid, "rating": "down"}).status_code == 403
    assert all(m["id"] != mid for m in app_client.get("/history").json())


def test_own_writes_succeed(emp1_client):
    item = emp1_client.get("/employees/EMP001/checklist").json()[0]
    r = emp1_client.patch(f"/employees/EMP001/checklist/{item['id']}", json={"done": not item["done"]})
    assert r.status_code == 200 and r.json()["done"] is (not item["done"])
    r = emp1_client.post("/employees/EMP001/tickets", json={"category": "IT", "subject": "VPN access", "description": "Need VPN access please."})
    assert r.status_code == 201 and r.json()["employee_id"] == "EMP001"


# ---------------------------------------------------------------- 9-10 roles and /ingest
def test_admin_has_no_employee_workspace(admin_client):
    me = admin_client.get("/auth/me").json()["user"]
    assert me["role"] == "admin" and me["employee_id"] is None
    assert admin_client.get("/employees/EMP001").status_code == 403
    assert admin_client.get("/history").status_code == 403
    assert admin_client.get("/employees/payroll/calendar").status_code == 200


def test_ingest_requires_admin_role_and_csrf(app_client, accounts):
    assert app_client.post("/ingest").status_code == 401
    login(app_client, accounts["emp1"])
    r = app_client.post("/ingest")
    assert r.status_code == 403 and r.json()["detail"] == "Administrator role required."
    login(app_client, accounts["admin"])
    token = app_client.headers.pop("X-CSRF-Token")
    assert app_client.post("/ingest").status_code == 403  # admin without CSRF token
    app_client.headers["X-CSRF-Token"] = token
    assert app_client.post("/ingest").json()["chunks"] > 40


# ---------------------------------------------------------------- 11 CSRF
@pytest.mark.parametrize("method, path, body", [
    ("POST", "/chat", {"question": "When is salary credited?"}),
    ("PATCH", "/employees/EMP001/checklist/1", {"done": True}),
    ("POST", "/employees/EMP001/tickets", {"category": "IT", "subject": "Subject", "description": "Description"}),
    ("POST", "/feedback", {"message_id": 1, "rating": "up"}),
    ("POST", "/escalate", {"question": "Help"}),
    ("POST", "/auth/logout", None),
])
def test_state_changing_requests_without_valid_csrf_token_are_rejected(emp1_client, accounts, method, path, body):
    good = emp1_client.headers.pop("X-CSRF-Token")
    r = emp1_client.request(method, path, json=body)
    assert r.status_code == 403 and r.json() == {"detail": "Missing or invalid CSRF token."}
    r = emp1_client.request(method, path, json=body, headers={"X-CSRF-Token": good[:-2] + "xx"})
    assert r.status_code == 403
    with new_client() as other:  # a token from another session is not valid for this one
        other_token = login(other, accounts["emp2"]).json()["csrf_token"]
    assert emp1_client.request(method, path, json=body, headers={"X-CSRF-Token": other_token}).status_code == 403
    assert emp1_client.get("/auth/me").status_code == 200  # still signed in (logout was rejected)


def test_safe_methods_do_not_need_csrf(emp1_client):
    emp1_client.headers.pop("X-CSRF-Token")
    assert emp1_client.get("/employees/EMP001/checklist").status_code == 200


# ---------------------------------------------------------------- 12 rate limiting
def test_login_rate_limited_per_email(app_client, accounts):
    bad = {"email": accounts["emp1"].email, "password": "wrong-password-000"}
    for _ in range(settings.login_max_failures_per_email):
        assert app_client.post("/auth/login", json=bad).status_code == 401
    r = app_client.post("/auth/login", json={"email": accounts["emp1"].email, "password": accounts["emp1"].password})
    assert r.status_code == 429 and int(r.headers["retry-after"]) > 0  # even the right password is refused while locked
    assert r.json()["detail"].startswith("Too many failed sign-in attempts")
    # Other accounts are unaffected.
    assert app_client.post("/auth/login", json={"email": accounts["emp2"].email, "password": accounts["emp2"].password}).status_code == 200


def test_login_rate_limited_per_ip_including_unknown_emails(app_client, accounts, monkeypatch):
    monkeypatch.setattr(settings, "login_max_failures_per_ip", 3)
    for i in range(3):
        assert app_client.post("/auth/login", json={"email": f"probe{i}@example.com", "password": "guess-guess-1"}).status_code == 401
    r = app_client.post("/auth/login", json={"email": accounts["emp2"].email, "password": accounts["emp2"].password})
    assert r.status_code == 429


def test_successful_login_resets_email_failures(app_client, accounts):
    bad = {"email": accounts["emp1"].email, "password": "wrong-password-000"}
    for _ in range(settings.login_max_failures_per_email - 1):
        app_client.post("/auth/login", json=bad)
    login(app_client, accounts["emp1"])
    for _ in range(settings.login_max_failures_per_email - 1):
        assert app_client.post("/auth/login", json=bad).status_code == 401


def test_forwarded_for_only_trusted_behind_proxy(app_client, accounts, monkeypatch):
    monkeypatch.setattr(settings, "login_max_failures_per_ip", 2)
    spoof = lambda n: {"X-Forwarded-For": f"203.0.113.{n}"}  # noqa: E731
    for n in range(2):
        app_client.post("/auth/login", json={"email": f"a{n}@example.com", "password": "x" * 12}, headers=spoof(n))
    # Untrusted: spoofed X-Forwarded-For is ignored, so the real client IP is limited.
    assert app_client.post("/auth/login", json={"email": "b@example.com", "password": "x" * 12}, headers=spoof(9)).status_code == 429
    auth.login_limiter.clear()
    monkeypatch.setattr(settings, "trust_proxy_headers", True)
    for _ in range(2):
        app_client.post("/auth/login", json={"email": "c@example.com", "password": "x" * 12},
                        headers={"X-Forwarded-For": "198.51.100.7"})
    assert app_client.post("/auth/login", json={"email": "d@example.com", "password": "x" * 12},
                           headers={"X-Forwarded-For": "198.51.100.8"}).status_code == 401


# ---------------------------------------------------------------- cookie Secure flag
def test_cookie_secure_over_https_and_when_forced(accounts, monkeypatch):
    with TestClient(app, base_url="https://testserver") as https_client:
        r = https_client.post("/auth/login", json={"email": accounts["emp1"].email, "password": accounts["emp1"].password})
        assert "Secure" in r.headers["set-cookie"]
    monkeypatch.setattr(settings, "session_cookie_secure", "true")
    with new_client() as c:
        r = c.post("/auth/login", json={"email": accounts["emp2"].email, "password": accounts["emp2"].password})
        assert "Secure" in r.headers["set-cookie"]


# ---------------------------------------------------------------- 14 RAG chat after authentication
def test_rag_and_employee_chat_work_when_authenticated(emp1_client, monkeypatch):
    monkeypatch.setattr(retriever, "search", lambda q, k=None: HITS)
    monkeypatch.setattr(llm, "generate_answer", lambda q, p: "Salary is credited on the last working day [Handbook 3].")
    r = emp1_client.post("/chat", json={"question": "When is my salary credited?", "employee_id": "EMP001"})
    assert r.status_code == 200 and r.json()["found"] is True
    assert r.json()["sources"] == [{"file": "handbook.md", "section": "3. Payroll", "score": 0.9}]
    r = emp1_client.post("/chat", json={"question": "What is my leave balance?"})
    assert r.status_code == 200 and r.json()["found"] is True and "Casual Leave" in r.json()["answer"]
    history = emp1_client.get("/history").json()
    assert [m["question"] for m in history] == ["What is my leave balance?", "When is my salary credited?"]


# ---------------------------------------------------------------- storage, hashing, provisioning
def test_passwords_stored_only_as_argon2id_hashes(accounts):
    with db._conn() as con:
        rows = [dict(r) for r in db._execute(con, "SELECT email, password_hash FROM user_accounts", all_rows=True)]
    assert len(rows) == 3
    for row in rows:
        assert row["password_hash"].startswith("$argon2id$")
        assert all(a.password not in row["password_hash"] for a in accounts.values())


def test_production_argon2_parameters_are_library_defaults():
    # The test-only fixture swaps auth._hasher; the PasswordHasher class itself is untouched.
    ph = PasswordHasher()
    assert (ph.time_cost, ph.memory_cost, ph.parallelism) == (3, 65536, 4)
    src = (settings.raw_dir.parent.parent / "backend" / "services" / "auth.py").read_text(encoding="utf-8")
    assert "_hasher = PasswordHasher()" in src  # no weakened parameters in production code


def test_account_rules(seeded_db):
    with pytest.raises(auth.AccountError):
        auth.upsert_account("short@example.com", "too-short", "EMP001")
    with pytest.raises(auth.AccountError):
        auth.upsert_account("noemp@example.com", "long-enough-password-1", None, "employee")
    with pytest.raises(auth.AccountError):
        auth.upsert_account("ghost@example.com", "long-enough-password-1", "EMP999")
    auth.upsert_account("first@example.com", "long-enough-password-1", "EMP003")
    with pytest.raises(auth.AccountError):  # one account per employee
        auth.upsert_account("second@example.com", "long-enough-password-1", "EMP003")


def test_provisioning_cli(seeded_db, monkeypatch, capsys):
    monkeypatch.setenv("TEST_NEW_PASSWORD", "cli-provisioned-password-77")
    assert manage_accounts.main(["set", "--email", "Rohan.Verma@example.com", "--employee-id", "EMP003",
                                 "--password-env", "TEST_NEW_PASSWORD"]) == 0
    assert manage_accounts.main(["set", "--email", "rohan.verma@example.com", "--employee-id", "EMP003",
                                 "--password-env", "TEST_NEW_PASSWORD"]) == 0  # idempotent
    assert manage_accounts.main(["list"]) == 0
    out = capsys.readouterr().out
    assert "rohan.verma@example.com" in out and "cli-provisioned-password-77" not in out and "$argon2" not in out
    assert auth.authenticate("rohan.verma@example.com", "cli-provisioned-password-77").employee_id == "EMP003"
    with pytest.raises(SystemExit):  # passwords are never accepted as arguments
        manage_accounts.main(["set", "--email", "x@example.com", "--employee-id", "EMP001", "--password", "abc"])
    monkeypatch.setattr(settings, "app_env", "production")
    with pytest.raises(SystemExit, match="production"):
        manage_accounts.main(["list"])
