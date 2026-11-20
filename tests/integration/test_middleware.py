import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import middleware


def make_app():
    app = FastAPI()
    middleware.install(app)

    @app.get("/ok")
    def ok():
        return {"ok": True}

    @app.get("/boom")
    def boom():
        raise RuntimeError("secret internal detail")

    @app.post("/echo")
    def echo(payload: dict):
        return payload

    return app


def test_request_id_header_and_logging(caplog):
    client = TestClient(make_app())
    with caplog.at_level(logging.INFO, logger="app"):
        r = client.get("/ok")
    assert r.status_code == 200
    rid = r.headers["X-Request-ID"]
    assert len(rid) == 8
    assert any(rid in rec.getMessage() and "/ok" in rec.getMessage() for rec in caplog.records)


def test_unhandled_error_returns_clean_json_500(caplog):
    client = TestClient(make_app(), raise_server_exceptions=False)
    with caplog.at_level(logging.INFO, logger="app"):
        r = client.get("/boom")
    assert r.status_code == 500
    body = r.json()
    assert body["detail"] == middleware.GENERIC_ERROR
    assert "secret" not in r.text
    assert body["request_id"] == r.headers["X-Request-ID"]
    assert any("unhandled error" in rec.getMessage() for rec in caplog.records)


def test_validation_error_is_friendly(env):
    from backend.main import app

    client = TestClient(app)
    r = client.post("/chat", json={"question": "   "})
    assert r.status_code == 422
    assert isinstance(r.json()["detail"], str) and "question" in r.json()["detail"].lower()
    assert "Value error" not in r.json()["detail"]
