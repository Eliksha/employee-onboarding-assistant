"""Final local verification: bidirectional employee isolation, post-logout rejection, response hygiene, SQL safety.

Complements test_auth.py. Isolated SQLite copy per test; synthetic accounts with random passwords.
"""
import re

import pytest
from fastapi.testclient import TestClient

from backend.config import ROOT, settings
from backend.main import app
from backend.services import employee_db, llm, retriever
from tests.conftest import login
from tests.integration.test_auth import PUBLIC, _all_api_routes

HITS = [{"source": "handbook.md", "section": "3. Payroll",
         "text": "3. Payroll: Salary is credited on the last working day of every month.", "score": 0.9}]
OTHER = {"emp1": "EMP002", "emp2": "EMP001"}
OWN = {"emp1": "EMP001", "emp2": "EMP002"}


@pytest.fixture
def two_clients(accounts):
    """Independent browser-like sessions for EMP001 and EMP002."""
    with TestClient(app, raise_server_exceptions=False) as c1, TestClient(app, raise_server_exceptions=False) as c2:
        login(c1, accounts["emp1"])
        login(c2, accounts["emp2"])
        yield {"emp1": c1, "emp2": c2}


@pytest.fixture
def fake_rag(monkeypatch):
    monkeypatch.setattr(retriever, "search", lambda q, k=None: HITS)
    monkeypatch.setattr(llm, "generate_answer", lambda q, p: "Salary is credited on the last working day [Handbook 3].")


# ---------------------------------------------------------------- bidirectional isolation
@pytest.mark.parametrize("who", ["emp1", "emp2"])
@pytest.mark.parametrize("suffix", ["", "/leave-balances", "/assets", "/checklist", "/tickets"])
def test_reads_of_the_other_employee_are_forbidden_in_both_directions(two_clients, who, suffix):
    client, other = two_clients[who], OTHER[who]
    r = client.get(f"/employees/{other}{suffix}")
    assert r.status_code == 403 and r.json() == {"detail": "You can only access your own records."}
    assert client.get(f"/history?employee_id={other}").status_code == 403
    assert client.get(f"/employees/{OWN[who]}{suffix}").status_code == 200


@pytest.mark.parametrize("who", ["emp1", "emp2"])
def test_writes_to_the_other_employee_are_forbidden_in_both_directions(two_clients, who):
    client, other = two_clients[who], OTHER[who]
    before = (employee_db.get_employee_checklist(other), employee_db.get_employee_tickets(other))
    assert client.patch(f"/employees/{other}/checklist/1", json={"done": True}).status_code == 403
    assert client.post(f"/employees/{other}/tickets",
                       json={"category": "IT", "subject": "Cross attempt", "description": "Must be rejected"}).status_code == 403
    assert client.post("/chat", json={"question": "What is my leave balance?", "employee_id": other}).status_code == 403
    assert (employee_db.get_employee_checklist(other), employee_db.get_employee_tickets(other)) == before


def test_checklist_updates_are_isolated_per_employee(two_clients):
    c1, c2 = two_clients["emp1"], two_clients["emp2"]
    item_id = c1.get("/employees/EMP001/checklist").json()[0]["id"]
    emp2_before = c2.get("/employees/EMP002/checklist").json()
    emp1_state = next(i["done"] for i in c1.get("/employees/EMP001/checklist").json() if i["id"] == item_id)
    r = c1.patch(f"/employees/EMP001/checklist/{item_id}", json={"done": not emp1_state})
    assert r.status_code == 200 and r.json()["done"] is (not emp1_state)
    assert c2.get("/employees/EMP002/checklist").json() == emp2_before      # same item id, other employee unchanged
    assert next(i["done"] for i in c1.get("/employees/EMP001/checklist").json() if i["id"] == item_id) is (not emp1_state)


def test_tickets_are_isolated_per_employee(two_clients):
    c1, c2 = two_clients["emp1"], two_clients["emp2"]
    created = c1.post("/employees/EMP001/tickets",
                      json={"category": "HR", "subject": "Isolation ticket", "description": "Only EMP001 may see this"}).json()
    assert created["employee_id"] == "EMP001"
    assert all(t["ticket_id"] != created["ticket_id"] for t in c2.get("/employees/EMP002/tickets").json())
    assert any(t["ticket_id"] == created["ticket_id"] for t in c1.get("/employees/EMP001/tickets").json())


def test_chat_history_and_feedback_are_isolated_in_both_directions(two_clients, fake_rag):
    c1, c2 = two_clients["emp1"], two_clients["emp2"]
    m1 = c1.post("/chat", json={"question": "When is my salary credited?"}).json()["message_id"]
    m2 = c2.post("/chat", json={"question": "When is my salary credited?"}).json()["message_id"]
    h1, h2 = c1.get("/history").json(), c2.get("/history").json()
    assert [m["id"] for m in h1] == [m1] and [m["id"] for m in h2] == [m2]
    assert {m["employee_id"] for m in h1} == {"EMP001"} and {m["employee_id"] for m in h2} == {"EMP002"}
    assert c1.post("/feedback", json={"message_id": m2, "rating": "down"}).status_code == 403
    assert c2.post("/feedback", json={"message_id": m1, "rating": "down"}).status_code == 403
    assert c1.post("/feedback", json={"message_id": m1, "rating": "up"}).status_code == 200
    assert c2.post("/feedback", json={"message_id": m2, "rating": "up"}).status_code == 200


# ---------------------------------------------------------------- post-logout rejection
@pytest.mark.parametrize("method, path", sorted(set(_all_api_routes()) - PUBLIC))
def test_every_protected_route_rejects_a_logged_out_session(app_client, accounts, method, path):
    login(app_client, accounts["emp1"])
    token = app_client.cookies.get(settings.session_cookie_name)
    assert app_client.post("/auth/logout").status_code == 200
    with TestClient(app, raise_server_exceptions=False) as replay:
        replay.cookies.set(settings.session_cookie_name, token)          # the old cookie, replayed
        replay.headers["X-CSRF-Token"] = app_client.headers["X-CSRF-Token"]  # and the old CSRF token
        url = path.replace("{employee_id}", "EMP001").replace("{item_id}", "1")
        assert replay.request(method, url, json={}).status_code == 401, f"{method} {path}"


# ---------------------------------------------------------------- no sensitive data in responses
SENSITIVE_KEYS = {"password", "password_hash", "token_hash", "session", "user_id", "pg_password", "groq_api_key"}


def _keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _keys(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from _keys(item)


def test_responses_never_expose_hashes_tokens_or_internal_ids(app_client, accounts, fake_rag):
    r = login(app_client, accounts["emp1"])
    token = app_client.cookies.get(settings.session_cookie_name)
    app_client.post("/chat", json={"question": "When is my salary credited?"})
    bodies = [r.text] + [app_client.get(p).text for p in (
        "/auth/me", "/employees/EMP001", "/employees/EMP001/checklist", "/employees/EMP001/tickets", "/history")]
    for text in bodies:
        assert "$argon2" not in text and token not in text and accounts["emp1"].password not in text
    import json as _json
    for text in bodies:
        assert not SENSITIVE_KEYS & set(_keys(_json.loads(text))), text[:120]


# ---------------------------------------------------------------- SQL safety (static)
def test_backend_sql_uses_bound_parameters_only():
    """No SQL statement may be assembled with f-strings, str.format or % interpolation."""
    offenders = []
    for path in (ROOT / "backend").rglob("*.py"):
        src = path.read_text(encoding="utf-8")
        for m in re.finditer(r'f"""\s*(SELECT|INSERT|UPDATE|DELETE)|f"(SELECT|INSERT|UPDATE|DELETE)', src):
            offenders.append(f"{path.name}: f-string SQL")
        for m in re.finditer(r"(_execute|\.execute|_rows|_insert_id)\([^)]*?(\.format\(|\"\s*%\s*\(|'\s*%\s*\()", src):
            offenders.append(f"{path.name}: formatted SQL")
    assert not offenders, offenders
