"""M5: feedback and escalation from chat answers (attribution, ownership, idempotency, history state)."""
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services import db, llm, retriever
from tests.conftest import login

HITS = [{"source": "handbook.pdf", "section": "2. Leave Policy > 2.1 Casual Leave", "page": 1,
         "text": "2. Leave Policy > 2.1 Casual Leave: Employees get 8 casual leaves per calendar year.", "score": 0.9}]


@pytest.fixture
def handbook(monkeypatch):
    monkeypatch.setattr(retriever, "search", lambda q, k=None: [dict(h) for h in HITS])
    monkeypatch.setattr(llm, "generate_answer", lambda q, p: "Employees get 8 casual leaves per calendar year [Handbook 2.1].")


@pytest.fixture
def two_clients(accounts):
    with TestClient(app, raise_server_exceptions=False) as c1, TestClient(app, raise_server_exceptions=False) as c2:
        login(c1, accounts["emp1"])
        login(c2, accounts["emp2"])
        yield c1, c2


def _escalation(escalation_id):
    with db._conn() as c:
        return dict(db._execute(c, "SELECT * FROM escalations WHERE id = ?", (escalation_id,), one=True))


def _ask(client, question="What is the leave policy?"):
    r = client.post("/chat", json={"question": question})
    assert r.status_code == 200
    return r.json()["message_id"]


def test_escalating_an_answer_is_attributed_and_idempotent(two_clients, handbook):
    c1, _ = two_clients
    mid = _ask(c1)
    r = c1.post("/escalate", json={"question": "What is the leave policy?", "message_id": mid})
    assert r.status_code == 200 and r.json()["status"] == "escalated to HR/IT (simulated)"
    row = _escalation(r.json()["id"])
    assert (row["employee_id"], row["message_id"], row["status"]) == ("EMP001", mid, "open")
    again = c1.post("/escalate", json={"question": "What is the leave policy?", "message_id": mid})
    assert again.status_code == 200 and again.json() == {"status": "already escalated to HR/IT (simulated)",
                                                         "id": r.json()["id"]}
    with db._conn() as c:
        assert db._execute(c, "SELECT COUNT(*) AS n FROM escalations", one=True)["n"] == 1


def test_free_text_escalation_still_works_and_is_attributed(two_clients):
    c1, _ = two_clients
    r = c1.post("/escalate", json={"question": "Need help with my visa", "contact_pref": "email"})
    assert r.status_code == 200
    row = _escalation(r.json()["id"])
    assert (row["employee_id"], row["message_id"], row["contact_pref"]) == ("EMP001", None, "email")


def test_cannot_escalate_or_rate_another_employees_answer(two_clients, handbook):
    c1, c2 = two_clients
    mid = _ask(c1)
    assert c2.post("/escalate", json={"question": "x", "message_id": mid}).status_code == 403
    assert c2.post("/feedback", json={"message_id": mid, "rating": "down"}).status_code == 403
    assert c2.post("/escalate", json={"question": "x", "message_id": 99999}).status_code == 404
    with db._conn() as c:
        assert db._execute(c, "SELECT COUNT(*) AS n FROM escalations", one=True)["n"] == 0


def test_escalation_and_feedback_require_csrf_and_a_session(app_client, accounts, handbook):
    login(app_client, accounts["emp1"])
    mid = _ask(app_client)
    token = app_client.headers.pop("X-CSRF-Token")
    assert app_client.post("/escalate", json={"question": "x", "message_id": mid}).status_code == 403
    assert app_client.post("/feedback", json={"message_id": mid, "rating": "up"}).status_code == 403
    app_client.headers["X-CSRF-Token"] = token
    with TestClient(app, raise_server_exceptions=False) as anonymous:
        assert anonymous.post("/escalate", json={"question": "x"}).status_code == 401


def test_admin_escalation_has_no_employee(admin_client):
    r = admin_client.post("/escalate", json={"question": "Index looks stale"})
    assert r.status_code == 200 and _escalation(r.json()["id"])["employee_id"] is None


@pytest.mark.parametrize("body", [{"question": ""}, {"question": "x" * 501}, {"question": "x", "message_id": "abc"},
                                  {"question": "x", "contact_pref": "y" * 101}])
def test_invalid_escalation_requests_are_rejected(two_clients, body):
    c1, _ = two_clients
    assert c1.post("/escalate", json=body).status_code == 422


def test_history_shows_latest_rating_and_escalation_state(two_clients, handbook):
    c1, c2 = two_clients
    m1, m2 = _ask(c1), _ask(c1, "How many casual leaves do I get in a year?")
    assert c1.post("/feedback", json={"message_id": m1, "rating": "up"}).status_code == 200
    assert c1.post("/feedback", json={"message_id": m1, "rating": "down"}).status_code == 200
    assert c1.post("/escalate", json={"question": "x", "message_id": m2}).status_code == 200
    history = {m["id"]: m for m in c1.get("/history").json()}
    assert (history[m1]["feedback"], history[m1]["escalated"]) == ("down", False)
    assert (history[m2]["feedback"], history[m2]["escalated"]) == (None, True)
    assert all(m["employee_id"] == "EMP001" for m in history.values())
    assert c2.get("/history").json() == []
    # existing history fields are unchanged
    assert {"id", "question", "answer", "found", "sources", "created_at", "employee_id"} <= set(history[m1])
