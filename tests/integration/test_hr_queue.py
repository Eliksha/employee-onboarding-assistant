"""HR/IT escalation queue: RBAC, privacy, status workflow, audit trail and the employee-side status (SQLite copy)."""
import secrets
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services import auth, db, retriever
from tests.conftest import login

HITS = [{"text": "Employees get 8 casual leaves per calendar year.", "source": "handbook.pdf",
         "section": "2. Leave Policy", "page": 2, "score": 0.9}]


@pytest.fixture
def hr_account(accounts):
    password = secrets.token_urlsafe(18)
    auth.upsert_account("hr.support@novatech.example", password, None, "hr")
    return SimpleNamespace(email="hr.support@novatech.example", password=password, employee_id=None, role="hr")


@pytest.fixture
def clients(accounts, hr_account, monkeypatch):
    from backend.services import llm

    monkeypatch.setattr(retriever, "search", lambda q, k=None: HITS)
    monkeypatch.setattr(llm, "generate_answer", lambda q, p: "Employees get 8 casual leaves per year [Handbook 2].")
    with TestClient(app, raise_server_exceptions=False) as emp1, TestClient(app, raise_server_exceptions=False) as emp2, \
            TestClient(app, raise_server_exceptions=False) as hr, TestClient(app, raise_server_exceptions=False) as admin:
        login(emp1, accounts["emp1"])
        login(emp2, accounts["emp2"])
        login(hr, hr_account)
        login(admin, accounts["admin"])
        yield SimpleNamespace(emp1=emp1, emp2=emp2, hr=hr, admin=admin)


def _escalate(client, question="How many casual leaves do I get?"):
    mid = client.post("/chat", json={"question": question}).json()["message_id"]
    r = client.post("/escalate", json={"question": question, "message_id": mid, "contact_pref": "email"})
    assert r.status_code == 200 and r.json()["status"] == "sent to the HR/IT support queue"
    return mid, r.json()["id"]


def test_only_hr_role_can_use_the_queue(clients):
    _escalate(clients.emp1)
    for client in (clients.emp1, clients.emp2, clients.admin):
        assert client.get("/hr/escalations").status_code == 403
        assert client.get("/hr/escalations/1").status_code == 403
        assert client.patch("/hr/escalations/1", json={"status": "in_progress"}).status_code == 403
    assert clients.hr.get("/hr/escalations").status_code == 200
    with TestClient(app, raise_server_exceptions=False) as anon:
        assert anon.get("/hr/escalations").status_code == 401


def test_hr_account_has_no_employee_workspace(clients):
    assert clients.hr.get("/employees/EMP001").status_code == 403
    assert clients.hr.get("/history").status_code == 403
    # Like administrator accounts, HR can ask general handbook questions but never act as an employee.
    assert clients.hr.post("/chat", json={"question": "What is my leave balance?", "employee_id": "EMP001"}
                           ).status_code == 403


def test_queue_shows_the_escalation_with_minimal_employee_data(clients):
    clients.emp1.post("/chat", json={"question": "What is my sick leave balance?"})   # not escalated
    mid, eid = _escalate(clients.emp1)
    r = clients.hr.get("/hr/escalations")
    assert r.headers["Cache-Control"] == "no-store"
    items = r.json()["items"]
    assert [i["id"] for i in items] == [eid]
    item = items[0]
    assert (item["employee_id"], item["employee_name"], item["status"], item["message_id"]) == (
        "EMP001", "Aarav Sharma", "open", mid)
    assert item["escalated_answer"].startswith("Employees get 8 casual leaves")
    # Only the escalated message is exposed: never other chat history, records, feedback or account data.
    text = r.text.lower()
    assert "sick leave balance" not in text and "password" not in text and "csrf" not in text
    assert set(item) == {"id", "question", "contact_pref", "status", "created_at", "updated_at", "resolution_note",
                         "employee_id", "employee_name", "message_id", "escalated_answer", "answer_sources",
                         "handled_by"}


def test_status_workflow_is_audited_and_visible_to_the_employee(clients):
    mid, eid = _escalate(clients.emp1)
    detail = clients.hr.get(f"/hr/escalations/{eid}").json()
    assert [e["action"] for e in detail["events"]] == ["created", "viewed"]
    r = clients.hr.patch(f"/hr/escalations/{eid}", json={"status": "in_progress", "note": "Checking with payroll"})
    assert r.status_code == 200 and r.json()["status"] == "in_progress"
    assert r.json()["handled_by"] == "hr.support@novatech.example"
    r = clients.hr.patch(f"/hr/escalations/{eid}", json={"status": "resolved", "note": "8 casual leaves confirmed"})
    events = r.json()["events"]
    changes = [(e["from_status"], e["to_status"], e["note"], e["actor"]) for e in events if e["action"] == "status_changed"]
    assert changes == [("open", "in_progress", "Checking with payroll", "hr.support@novatech.example"),
                       ("in_progress", "resolved", "8 casual leaves confirmed", "hr.support@novatech.example")]
    assert r.json()["resolution_note"] == "8 casual leaves confirmed"
    history = {m["id"]: m for m in clients.emp1.get("/history").json()}
    assert (history[mid]["escalated"], history[mid]["escalation_status"]) == (True, "resolved")
    assert [i["id"] for i in clients.hr.get("/hr/escalations", params={"status": "resolved"}).json()["items"]] == [eid]
    assert clients.hr.get("/hr/escalations", params={"status": "open"}).json()["items"] == []


@pytest.mark.parametrize("path", [("open", "closed"), ("in_progress", "in_progress")])
def test_invalid_transitions_are_rejected_and_change_nothing(clients, path):
    _, eid = _escalate(clients.emp1)
    if path[0] != "open":
        assert clients.hr.patch(f"/hr/escalations/{eid}", json={"status": path[0]}).status_code == 200
    r = clients.hr.patch(f"/hr/escalations/{eid}", json={"status": path[1]})
    assert r.status_code == 409 and "Cannot change status" in r.json()["detail"]
    assert clients.hr.get(f"/hr/escalations/{eid}").json()["status"] == path[0]


def test_closed_is_final_and_unknown_status_or_id_are_rejected(clients):
    _, eid = _escalate(clients.emp1)
    for status in ("resolved", "closed"):
        assert clients.hr.patch(f"/hr/escalations/{eid}", json={"status": status}).status_code == 200
    assert clients.hr.patch(f"/hr/escalations/{eid}", json={"status": "open"}).status_code == 409
    assert clients.hr.patch(f"/hr/escalations/{eid}", json={"status": "deleted"}).status_code == 422
    assert clients.hr.patch("/hr/escalations/9999", json={"status": "resolved"}).status_code == 404
    assert clients.hr.get("/hr/escalations/9999").status_code == 404


def test_status_change_requires_csrf_and_bounded_note(clients):
    _, eid = _escalate(clients.emp1)
    token = clients.hr.headers.pop("X-CSRF-Token")
    assert clients.hr.patch(f"/hr/escalations/{eid}", json={"status": "resolved"}).status_code == 403
    clients.hr.headers["X-CSRF-Token"] = token
    assert clients.hr.patch(f"/hr/escalations/{eid}", json={"status": "resolved", "note": "x" * 1001}).status_code == 422
    assert clients.hr.get(f"/hr/escalations/{eid}").json()["status"] == "open"


def test_concurrent_change_is_detected(clients, monkeypatch):
    _, eid = _escalate(clients.emp1)
    real_execute = db._execute

    def racing(con, query, params=(), **kw):   # another HR user changes the status between read and update
        if query.lstrip().startswith("UPDATE escalations SET status"):
            real_execute(con, "UPDATE escalations SET status = ? WHERE id = ?", ("in_progress", eid))
        return real_execute(con, query, params, **kw)

    monkeypatch.setattr(db, "_execute", racing)
    r = clients.hr.patch(f"/hr/escalations/{eid}", json={"status": "resolved"})
    assert r.status_code == 409 and "changed by someone else" in r.json()["detail"]


def test_employee_still_cannot_escalate_someone_elses_answer(clients):
    mid, _ = _escalate(clients.emp1)
    assert clients.emp2.post("/escalate", json={"question": "x", "message_id": mid}).status_code == 403
    assert len(clients.hr.get("/hr/escalations").json()["items"]) == 1
