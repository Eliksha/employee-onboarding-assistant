"""Step 7: logging and error-handling tests (isolated SQLite, no network, no real LLM)."""
import logging
import sqlite3

import psycopg2
import pytest
from fastapi.testclient import TestClient

from backend import logging_config, middleware
from backend.config import ROOT, settings
from backend.main import app
from backend.routes import chat as chat_route
from backend.services import db, employee_db, llm, orchestrator, retriever

FAKE_KEY = "gsk_FAKEKEYStep7LoggingTest0123456789"
FAKE_PW = "FakePgPassword-Step7!"
QUESTION = "Synthetic private question 4711 about my salary"
HITS = [{"source": "handbook.md", "section": "3. Payroll",
         "text": "3. Payroll: Salary is credited on the last working day of every month.", "score": 0.9}]


@pytest.fixture
def client(emp1_client, monkeypatch):
    """Signed-in employee (EMP001); fake secrets so leakage checks have something to look for."""
    monkeypatch.setattr(settings, "groq_api_key", FAKE_KEY)
    monkeypatch.setattr(settings, "pg_password", FAKE_PW)
    return emp1_client


def _all_log_text(caplog):
    parts = []
    for rec in caplog.records:
        parts.append(rec.getMessage())
        if rec.exc_info:
            parts.append(logging.Formatter().formatException(rec.exc_info))
    return "\n".join(parts)


def _assert_safe_500(r):
    assert r.status_code == 500
    assert r.json() == {"detail": middleware.GENERIC_ERROR, "request_id": r.headers["X-Request-ID"]}
    assert "Traceback" not in r.text and "Error" not in r.json()["detail"]


# ---------------------------------------------------------------- configuration
def test_tests_do_not_write_to_real_log_directory():
    assert settings.log_dir.resolve() != (ROOT / "logs").resolve()


def test_log_format_includes_request_id():
    record = logging.LogRecord("app", logging.INFO, __file__, 1, "hello", None, None)
    logging_config.RequestIdFilter().filter(record)
    assert logging.Formatter(logging_config._FORMAT).format(record).endswith("| INFO | rid=- | hello")


# ---------------------------------------------------------------- request-ID correlation
def test_service_level_logs_carry_the_request_id(client, monkeypatch, caplog):
    monkeypatch.setattr(retriever, "search", lambda q, k=None: HITS)

    def unavailable(q, p):
        raise llm.LLMUnavailable("Error code: 401 - Invalid API Key")

    monkeypatch.setattr(llm, "generate_answer", unavailable)
    with caplog.at_level(logging.INFO, logger="app"):
        r = client.post("/chat", json={"question": QUESTION})
    assert r.status_code == 503 and isinstance(r.json()["detail"], str)
    rid = r.headers["X-Request-ID"]
    rec = next(x for x in caplog.records if x.getMessage().startswith("LLM unavailable"))
    assert rec.request_id == rid and rec.levelno == logging.WARNING


def test_request_id_resets_after_request(client, caplog):
    client.get("/health")
    with caplog.at_level(logging.INFO, logger="app"):
        logging.getLogger("app").info("outside request")
    assert caplog.records[-1].request_id == "-"


# ---------------------------------------------------------------- failure classes
def test_database_failure_on_employee_endpoint_is_safe_500_and_logged(client, monkeypatch, caplog):
    def down(*a, **k):
        raise psycopg2.OperationalError(f"connection to server failed (password={FAKE_PW})")

    monkeypatch.setattr(employee_db, "get_employee", down)
    with caplog.at_level(logging.INFO, logger="app"):
        r = client.get("/employees/EMP001")
    _assert_safe_500(r)
    assert FAKE_PW not in r.text and "OperationalError" not in r.text
    err = next(x for x in caplog.records if "unhandled error" in x.getMessage())
    assert err.exc_info and err.request_id == r.headers["X-Request-ID"]


def test_database_failure_on_history_and_feedback(client, monkeypatch):
    monkeypatch.setattr(chat_route, "get_employee", lambda *_: (_ for _ in ()).throw(psycopg2.OperationalError("down")))
    _assert_safe_500(client.get("/history", params={"employee_id": "EMP001"}))
    monkeypatch.setattr(db, "get_message_owner", lambda *_: (_ for _ in ()).throw(sqlite3.OperationalError("locked")))
    _assert_safe_500(client.post("/feedback", json={"message_id": 1, "rating": "up"}))


def test_llm_unavailable_returns_503(client, monkeypatch):
    monkeypatch.setattr(retriever, "search", lambda q, k=None: HITS)
    monkeypatch.setattr(llm, "generate_answer", lambda q, p: (_ for _ in ()).throw(llm.LLMUnavailable("timeout")))
    r = client.post("/chat", json={"question": "When is salary credited?"})
    assert r.status_code == 503
    assert r.json() == {"detail": "The AI service is temporarily unavailable. Please try again shortly."}


@pytest.mark.parametrize("exc", [RuntimeError("faiss index corrupt"), ValueError("embedding dim mismatch")])
def test_retrieval_failure_is_server_error_not_client_error(client, monkeypatch, caplog, exc):
    """Previously a ValueError inside retrieval was reported as 400 'Invalid employee or query.'."""
    monkeypatch.setattr(retriever, "search", lambda q, k=None: (_ for _ in ()).throw(exc))
    with caplog.at_level(logging.INFO, logger="app"):
        r = client.post("/chat", json={"question": "When is salary credited?"})
    _assert_safe_500(r)
    assert str(exc) not in r.text
    assert any(x.exc_info for x in caplog.records if "unhandled error" in x.getMessage())


def test_unknown_employee_inside_pipeline_is_still_400(client, monkeypatch):
    # The session employee passes the route check but vanishes before the pipeline runs.
    monkeypatch.setattr(chat_route, "get_employee", lambda *_: {"employee_id": "EMP001"})
    monkeypatch.setattr(orchestrator, "get_employee", lambda *_: None)
    r = client.post("/chat", json={"question": "What is my leave balance?"})
    assert r.status_code == 400 and r.json() == {"detail": "Invalid employee or query."}


def test_unknown_employee_error_remains_a_value_error():
    assert issubclass(employee_db.UnknownEmployeeError, ValueError)


# ---------------------------------------------------------------- invalid requests
@pytest.mark.parametrize("kwargs, status, fragment", [
    ({"content": b"{bad json", "headers": {"content-type": "application/json"}}, 422, "not valid JSON"),
    ({"json": {}}, 422, "question"),
    ({"json": {"question": "x" * 501}}, 422, "500"),
])
def test_invalid_chat_requests_return_readable_string_detail(client, kwargs, status, fragment):
    r = client.post("/chat", **kwargs)
    assert r.status_code == status
    assert isinstance(r.json()["detail"], str) and fragment in r.json()["detail"]
    assert "X-Request-ID" in r.headers


def test_unknown_route_and_method_are_json(client):
    assert client.get("/does-not-exist").json() == {"detail": "Not Found"}
    assert client.delete("/health").json() == {"detail": "Method Not Allowed"}


# ---------------------------------------------------------------- no secrets / sensitive text in logs
def test_logs_contain_no_secrets_or_question_text(client, accounts, monkeypatch, caplog):
    monkeypatch.setattr(retriever, "search", lambda q, k=None: HITS)
    monkeypatch.setattr(llm, "generate_answer", lambda q, p: "Salary is credited on the last working day [Handbook 3].")
    with caplog.at_level(logging.DEBUG, logger="app"):
        ok = client.post("/chat", json={"question": QUESTION})
        monkeypatch.setattr(llm, "generate_answer", lambda q, p: (_ for _ in ()).throw(llm.LLMUnavailable("401")))
        client.post("/chat", json={"question": QUESTION})
        monkeypatch.setattr(retriever, "search", lambda q, k=None: (_ for _ in ()).throw(RuntimeError("boom")))
        client.post("/chat", json={"question": QUESTION})
        client.post("/chat", json={"question": QUESTION + "x" * 500})
        client.post("/auth/login", json={"email": accounts["emp2"].email, "password": "wrong-" + accounts["emp2"].password})
        relog = client.post("/auth/login", json={"email": accounts["emp1"].email, "password": accounts["emp1"].password})
    assert ok.status_code == 200 and ok.json()["found"] is True
    text = _all_log_text(caplog)
    assert "chat answered" in text and "unhandled error" in text and "login failed" in text
    session_cookie = relog.cookies.get(settings.session_cookie_name) or client.cookies.get(settings.session_cookie_name)
    secrets_to_check = (FAKE_KEY, FAKE_PW, "gsk_", QUESTION, "4711", accounts["emp1"].password,
                        accounts["emp2"].password, accounts["emp2"].email, relog.json()["csrf_token"], session_cookie)
    for secret in secrets_to_check:
        assert secret not in text, f"log leaked: {secret[:6]}..."
