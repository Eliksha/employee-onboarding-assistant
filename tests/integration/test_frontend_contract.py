"""Frontend <-> backend contract checks (Step 6).

Parses frontend/src/api.js so that renamed/removed backend routes, or a frontend call to a
route that does not exist, fail in CI before reaching the browser. Uses the isolated SQLite DB.
"""
import re

import pytest
from fastapi.testclient import TestClient

from backend.config import ROOT
from backend.main import app
from backend.schemas.models import ChatRequest

API_JS = ROOT / "frontend" / "src" / "api.js"
FORMAT_JS = ROOT / "frontend" / "src" / "format.js"
CALL_RE = re.compile(r"api\.(get|post|patch|put|delete)\(\s*[`'\"]([^`'\"]+)[`'\"]")


def frontend_calls():
    calls = []
    for method, path in CALL_RE.findall(API_JS.read_text(encoding="utf-8")):
        calls.append((method.upper(), re.sub(r"\$\{[^}]+\}", "{param}", path)))
    return calls


def backend_routes():
    routes = []
    for path, ops in app.openapi()["paths"].items():
        for method in ops:
            routes.append((method.upper(), re.sub(r"\{[^}]+\}", "{param}", path)))
    return routes


def test_api_js_is_parsed():
    assert len(frontend_calls()) == 13


@pytest.mark.parametrize("call", frontend_calls(), ids=lambda c: f"{c[0]} {c[1]}")
def test_every_frontend_call_has_a_backend_route(call):
    assert call in backend_routes(), f"frontend calls {call}, backend has no such route"


def test_static_payroll_route_not_shadowed_by_employee_id_route(emp1_client, monkeypatch):
    from backend.services import employee_db

    monkeypatch.setattr(employee_db, "get_payroll_calendar", lambda: [{"payroll_month": "2099-01"}])
    body = emp1_client.get("/employees/payroll/calendar")
    assert body.status_code == 200 and body.json() == [{"payroll_month": "2099-01"}]


def test_chat_length_limit_matches_frontend():
    backend_max = next(m.max_length for m in ChatRequest.model_fields["question"].metadata if hasattr(m, "max_length"))
    frontend_max = int(re.search(r"CHAT_MAX_LENGTH\s*=\s*(\d+)", FORMAT_JS.read_text(encoding="utf-8")).group(1))
    assert frontend_max == backend_max == 500


def test_error_responses_use_string_detail_for_frontend(emp1_client):
    """The UI renders `detail` directly, so validation errors must be readable strings, not arrays."""
    r = emp1_client.post("/chat", json={"question": "x" * 501})
    assert r.status_code == 422 and isinstance(r.json()["detail"], str)
