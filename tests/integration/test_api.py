"""Core API behaviour, exercised as an authenticated user (see tests/conftest.py)."""
from backend.services import llm, retriever


def test_health(app_client):
    assert app_client.get("/health").json() == {"status": "ok"}


def test_chat_grounded_answer(emp1_client, monkeypatch, env):
    monkeypatch.setattr(env, "similarity_threshold", 0.1)
    monkeypatch.setattr(llm, "generate_answer", lambda q, p: "You get 8 casual leaves per year [Handbook 2.1].")
    r = emp1_client.post("/chat", json={"question": "How many casual leaves do I get in a year?"})
    assert r.status_code == 200
    body = r.json()
    assert body["found"] is True and body["sources"] and "8" in body["answer"]


def test_chat_fallback_when_score_low_skips_llm(emp1_client, monkeypatch):
    monkeypatch.setattr(retriever, "search", lambda q, k=None: [{"text": "x", "source": "handbook.md", "section": "s", "score": 0.1}])

    def boom(*a, **k):
        raise AssertionError("LLM must not be called below the threshold")

    monkeypatch.setattr(llm, "generate_answer", boom)
    body = emp1_client.post("/chat", json={"question": "What is the weather in Mumbai?"}).json()
    assert body["found"] is False and body["sources"] == []


def test_chat_fallback_when_llm_says_not_found(emp1_client, monkeypatch, env):
    monkeypatch.setattr(env, "similarity_threshold", 0.0)
    monkeypatch.setattr(llm, "generate_answer", lambda q, p: "NOT_FOUND")
    assert emp1_client.post("/chat", json={"question": "Tell me everyone's salary"}).json()["found"] is False


def test_chat_validation_and_llm_error(emp1_client, monkeypatch, env):
    assert emp1_client.post("/chat", json={"question": "   "}).status_code == 422
    assert emp1_client.post("/chat", json={"question": "x" * 501}).status_code == 422
    monkeypatch.setattr(env, "similarity_threshold", 0.0)

    def fail(q, p):
        raise llm.LLMUnavailable("down")

    monkeypatch.setattr(llm, "generate_answer", fail)
    assert emp1_client.post("/chat", json={"question": "How many casual leaves?"}).status_code == 503


def test_legacy_checklist_is_admin_only(admin_client, app_client, accounts):
    items = admin_client.get("/checklist").json()
    assert len(items) == 15
    first = items[0]
    assert admin_client.patch(f"/checklist/{first['id']}", json={"done": not first["done"]}).json()["done"] is (not first["done"])
    assert admin_client.patch("/checklist/999", json={"done": True}).status_code == 404

    from tests.conftest import login

    login(app_client, accounts["emp1"])  # same client, now an employee session
    assert app_client.get("/checklist").status_code == 403
    assert app_client.patch("/checklist/1", json={"done": True}).status_code == 403


def test_feedback_and_escalate(emp1_client, monkeypatch, env):
    monkeypatch.setattr(env, "similarity_threshold", 0.0)
    monkeypatch.setattr(llm, "generate_answer", lambda q, p: "8 per year")
    mid = emp1_client.post("/chat", json={"question": "casual leaves"}).json()["message_id"]
    assert emp1_client.post("/feedback", json={"message_id": mid, "rating": "up"}).status_code == 200
    assert emp1_client.post("/feedback", json={"message_id": 9999, "rating": "up"}).status_code == 404
    assert emp1_client.post("/feedback", json={"message_id": mid, "rating": "meh"}).status_code == 422
    assert emp1_client.post("/escalate", json={"question": "Need help with visa"}).status_code == 200
    history = emp1_client.get("/history").json()
    assert isinstance(history, list) and len(history) == 1 and history[0]["id"] == mid


def test_reindex_requires_admin(admin_client, app_client, accounts):
    assert admin_client.post("/ingest").json()["chunks"] > 40

    from tests.conftest import login

    login(app_client, accounts["emp1"])
    assert app_client.post("/ingest").status_code == 403
