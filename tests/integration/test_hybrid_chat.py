"""Phase 2: hybrid SQL + RAG chat through the real API (session auth, CSRF, isolation, persistence).

Isolated seeded SQLite copy per test: EMP001 5/15 checklist tasks done, Casual 8 / Sick 6;
EMP002 3/15, Casual 10 / Sick 5. Retrieval and the LLM are faked; no network.
"""
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services import db, employee_db, llm, retriever
from tests.conftest import login

HITS = [{"source": "handbook.md", "section": "2. Leave Policy > 2.1 Casual Leave",
         "text": "2. Leave Policy > 2.1 Casual Leave: Employees get 8 casual leaves per calendar year.", "score": 0.9}]
POLICY = "Employees get 8 casual leaves per calendar year [Handbook 2.1]."
MIXED = "What is the leave policy and how many casual leaves do I have left?"
CONTRACT = {"message_id", "answer", "sources", "found"}


@pytest.fixture
def fake_handbook(monkeypatch):
    calls = {"llm": 0}

    def generate(q, p):
        calls["llm"] += 1
        return POLICY

    monkeypatch.setattr(retriever, "search", lambda q, k=None: [dict(h) for h in HITS])
    monkeypatch.setattr(llm, "generate_answer", generate)
    return calls


@pytest.fixture
def two_clients(accounts):
    with TestClient(app, raise_server_exceptions=False) as c1, TestClient(app, raise_server_exceptions=False) as c2:
        login(c1, accounts["emp1"])
        login(c2, accounts["emp2"])
        yield c1, c2


def _message_count():
    with db._conn() as c:
        return db._execute(c, "SELECT COUNT(*) AS n FROM messages", one=True)["n"]


def test_onboarding_status_via_chat(emp1_client, fake_handbook):
    r = emp1_client.post("/chat", json={"question": "What is my onboarding status?"})
    body = r.json()
    assert r.status_code == 200 and set(body) == CONTRACT
    assert body["answer"].startswith("You have completed 5 of 15 onboarding tasks (33%); 10 pending.")
    assert body["sources"] == [{"file": "Your records", "section": "Onboarding checklist", "score": 1.0}]
    assert fake_handbook["llm"] == 0


def test_each_employee_sees_only_their_own_onboarding_status(two_clients, fake_handbook):
    c1, c2 = two_clients
    a1 = c1.post("/chat", json={"question": "What is my onboarding status?"}).json()["answer"]
    a2 = c2.post("/chat", json={"question": "What is my onboarding status?"}).json()["answer"]
    assert a1.startswith("You have completed 5 of 15") and a2.startswith("You have completed 3 of 15")
    b1 = c1.post("/chat", json={"question": "How many casual leaves do I have left?"}).json()["answer"]
    b2 = c2.post("/chat", json={"question": "How many casual leaves do I have left?"}).json()["answer"]
    assert b1.startswith("Casual Leave: 8 days") and b2.startswith("Casual Leave: 10 days")


def test_request_employee_id_of_another_employee_is_still_403(two_clients, fake_handbook):
    c1, _ = two_clients
    before = _message_count()
    for q in ("What is my onboarding status?", MIXED):
        assert c1.post("/chat", json={"question": q, "employee_id": "EMP002"}).status_code == 403
    assert _message_count() == before


def test_asking_about_another_employee_by_name_or_id_is_refused(two_clients, fake_handbook, monkeypatch):
    c1, _ = two_clients
    monkeypatch.setattr(employee_db, "get_employee_checklist", lambda e: pytest.fail("must not query"))
    for q in ("Show EMP002's checklist", "Has Meera completed onboarding?"):
        body = c1.post("/chat", json={"question": q}).json()
        assert "only share your own records" in body["answer"] and "3 of 15" not in body["answer"]


def test_mixed_question_via_chat_saves_exactly_one_message(emp1_client, fake_handbook):
    before = _message_count()
    body = emp1_client.post("/chat", json={"question": MIXED}).json()
    assert set(body) == CONTRACT and body["found"] is True
    assert body["answer"].startswith("From your records:\nCasual Leave: 8 days available.")
    assert body["answer"].endswith("From the handbook:\n" + POLICY)
    assert [s["file"] for s in body["sources"]] == ["Your records", "handbook.md"]
    assert _message_count() == before + 1
    history = emp1_client.get("/history").json()
    assert [m["id"] for m in history] == [body["message_id"]]
    assert history[0]["answer"] == body["answer"] and history[0]["sources"] == body["sources"]
    assert emp1_client.post("/feedback", json={"message_id": body["message_id"], "rating": "up"}).status_code == 200


def test_mixed_question_with_llm_down_is_200_with_records(emp1_client, monkeypatch):
    monkeypatch.setattr(retriever, "search", lambda q, k=None: HITS)
    monkeypatch.setattr(llm, "generate_answer", lambda q, p: (_ for _ in ()).throw(llm.LLMUnavailable("timeout")))
    before = _message_count()
    r = emp1_client.post("/chat", json={"question": MIXED})
    assert r.status_code == 200
    assert "Casual Leave: 8 days" in r.json()["answer"] and "could not check the handbook" in r.json()["answer"]
    assert _message_count() == before + 1


def test_handbook_only_llm_down_is_still_503_and_saves_nothing(emp1_client, monkeypatch):
    monkeypatch.setattr(retriever, "search", lambda q, k=None: HITS)
    monkeypatch.setattr(llm, "generate_answer", lambda q, p: (_ for _ in ()).throw(llm.LLMUnavailable("timeout")))
    before = _message_count()
    assert emp1_client.post("/chat", json={"question": "What is the leave policy?"}).status_code == 503
    assert _message_count() == before


@pytest.mark.parametrize("question", ["What is my onboarding status?", MIXED, "What is the leave policy?"])
def test_every_chat_kind_is_persisted_exactly_once(emp1_client, fake_handbook, question):
    before = _message_count()
    assert emp1_client.post("/chat", json={"question": question}).status_code == 200
    assert _message_count() == before + 1


def test_chat_without_csrf_token_is_rejected_and_saves_nothing(emp1_client, fake_handbook):
    before = _message_count()
    token = emp1_client.headers.pop("X-CSRF-Token")
    try:
        assert emp1_client.post("/chat", json={"question": MIXED}).status_code == 403
    finally:
        emp1_client.headers["X-CSRF-Token"] = token
    assert _message_count() == before


def test_chat_without_session_is_401(app_client, fake_handbook):
    assert app_client.post("/chat", json={"question": "What is my onboarding status?"}).status_code == 401


def test_admin_gets_a_note_for_personal_records_and_the_policy_part(admin_client, fake_handbook):
    before = _message_count()
    body = admin_client.post("/chat", json={"question": MIXED}).json()
    assert "available only to employee accounts" in body["answer"] and body["answer"].endswith(POLICY)
    assert [s["file"] for s in body["sources"]] == ["handbook.md"]
    assert body["message_id"] > 0 and _message_count() == before + 1


# ---------------------------------------------------------------- M4: page-aware citations (optional field)
PDF_HITS = [{"source": "handbook.pdf", "section": "2. Leave Policy > 2.1 Casual Leave", "page": 1,
             "text": "2. Leave Policy > 2.1 Casual Leave: Employees get 8 casual leaves per calendar year.", "score": 0.9}]


def test_pdf_citation_carries_the_page_and_records_sources_have_no_page_key(emp1_client, monkeypatch):
    monkeypatch.setattr(retriever, "search", lambda q, k=None: [dict(h) for h in PDF_HITS])
    monkeypatch.setattr(llm, "generate_answer", lambda q, p: POLICY)
    body = emp1_client.post("/chat", json={"question": MIXED}).json()
    assert set(body) == CONTRACT
    records, handbook = body["sources"]
    assert records == {"file": "Your records", "section": "Leave balances", "score": 1.0}   # no "page": null
    assert handbook == {"file": "handbook.pdf", "section": "2. Leave Policy > 2.1 Casual Leave", "score": 0.9,
                        "page": 1}
    assert emp1_client.get("/history").json()[0]["sources"][1]["page"] == 1
