import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services import llm, retriever


@pytest.fixture
def client(env):
    with TestClient(app) as c:
        yield c


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_chat_grounded_answer(client, monkeypatch, env):
    monkeypatch.setattr(env, "similarity_threshold", 0.1)
    monkeypatch.setattr(llm, "generate_answer", lambda q, p: "You get 8 casual leaves per year [Handbook 2.1].")
    r = client.post("/chat", json={"question": "How many casual leaves do I get in a year?"})
    assert r.status_code == 200
    body = r.json()
    assert body["found"] is True and body["sources"] and "8" in body["answer"]


def test_chat_fallback_when_score_low_skips_llm(client, monkeypatch):
    monkeypatch.setattr(retriever, "search", lambda q, k=None: [{"text": "x", "source": "handbook.md", "section": "s", "score": 0.1}])

    def boom(*a, **k):
        raise AssertionError("LLM must not be called below the threshold")

    monkeypatch.setattr(llm, "generate_answer", boom)
    body = client.post("/chat", json={"question": "What is the weather in Mumbai?"}).json()
    assert body["found"] is False and body["sources"] == []


def test_chat_fallback_when_llm_says_not_found(client, monkeypatch, env):
    monkeypatch.setattr(env, "similarity_threshold", 0.0)
    monkeypatch.setattr(llm, "generate_answer", lambda q, p: "NOT_FOUND")
    assert client.post("/chat", json={"question": "Tell me everyone's salary"}).json()["found"] is False


def test_chat_validation_and_llm_error(client, monkeypatch, env):
    assert client.post("/chat", json={"question": "   "}).status_code == 422
    assert client.post("/chat", json={"question": "x" * 501}).status_code == 422
    monkeypatch.setattr(env, "similarity_threshold", 0.0)

    def fail(q, p):
        raise llm.LLMUnavailable("down")

    monkeypatch.setattr(llm, "generate_answer", fail)
    assert client.post("/chat", json={"question": "How many casual leaves?"}).status_code == 503


def test_checklist_flow(client):
    items = client.get("/checklist").json()
    assert len(items) == 15 and not any(i["done"] for i in items)
    assert client.patch("/checklist/1", json={"done": True}).json()["done"] is True
    assert client.get("/checklist").json()[0]["done"] is True
    assert client.patch("/checklist/999", json={"done": True}).status_code == 404


def test_feedback_and_escalate(client, monkeypatch, env):
    monkeypatch.setattr(env, "similarity_threshold", 0.0)
    monkeypatch.setattr(llm, "generate_answer", lambda q, p: "8 per year")
    mid = client.post("/chat", json={"question": "casual leaves"}).json()["message_id"]
    assert client.post("/feedback", json={"message_id": mid, "rating": "up"}).status_code == 200
    assert client.post("/feedback", json={"message_id": 9999, "rating": "up"}).status_code == 404
    assert client.post("/feedback", json={"message_id": mid, "rating": "meh"}).status_code == 422
    assert client.post("/escalate", json={"question": "Need help with visa"}).status_code == 200
    assert len(client.get("/history").json()) == 1


def test_reindex(client):
    assert client.post("/ingest").json()["chunks"] > 40
