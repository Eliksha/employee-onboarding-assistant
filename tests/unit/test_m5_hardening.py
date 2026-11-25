"""M5: API documentation exposure, nginx security headers, fresh-install integrity SQL vs migration 007."""
import re

import pytest

from backend import main
from backend.config import ROOT, settings
from backend.services import db_integrity

NGINX = (ROOT / "frontend" / "nginx.conf").read_text(encoding="utf-8")
COMPOSE = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
INTEGRITY_SQL = (ROOT / "docker" / "postgres" / "04_integrity.sql").read_text(encoding="utf-8")


@pytest.mark.parametrize("app_env, api_docs, expected", [
    ("development", None, True), ("production", None, False), ("staging", None, False),
    ("development", False, False), ("production", True, True), (" Development ", None, True),
])
def test_api_docs_only_in_development_unless_explicitly_set(monkeypatch, app_env, api_docs, expected):
    monkeypatch.setattr(settings, "app_env", app_env)
    monkeypatch.setattr(settings, "api_docs", api_docs)
    assert main.docs_enabled() is expected


def test_containerised_backend_disables_api_docs():
    assert re.search(r'^\s+API_DOCS: "false"', COMPOSE, re.M)


@pytest.mark.parametrize("header, value", [
    ("Content-Security-Policy", "default-src 'self'; script-src 'self';"),
    ("Content-Security-Policy", "frame-ancestors 'none'"),
    ("Content-Security-Policy", "object-src 'none'"),
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("Referrer-Policy", "no-referrer"),
    ("Permissions-Policy", "camera=()"),
    ("Cross-Origin-Opener-Policy", "same-origin"),
])
def test_nginx_sends_security_headers_on_every_response(header, value):
    line = next(l for l in NGINX.splitlines() if l.strip().startswith(f"add_header {header} "))
    assert value in line and line.rstrip().endswith("always;")


def test_nginx_header_inheritance_is_not_broken_and_docs_are_blocked():
    server_level = re.split(r"\n\s*location ", NGINX, maxsplit=1)[0]
    assert NGINX.count("add_header") == server_level.count("add_header")  # no location overrides them
    assert "server_tokens off;" in server_level
    assert re.search(r"location ~ \^/api/\(docs\|redoc\|openapi\\\.json\)\$ \{\s*return 404;", NGINX)
    assert "unsafe-eval" not in NGINX and "script-src 'self';" in NGINX


def test_fresh_install_sql_matches_migration_007():
    for table, column, kind in db_integrity.COLUMNS:
        assert f"ALTER TABLE public.{table} ADD COLUMN IF NOT EXISTS {column} {kind};" in INTEGRITY_SQL
    for name, (table, definition) in db_integrity.CONSTRAINTS.items():
        assert re.search(rf"ALTER TABLE ONLY public\.{table}\s+ADD CONSTRAINT {name} {re.escape(definition)};",
                         INTEGRITY_SQL), name
    for name, (table, column) in db_integrity.INDEXES.items():
        assert f"CREATE INDEX IF NOT EXISTS {name} ON public.{table} ({column});" in INTEGRITY_SQL
    assert "ALTER TABLE public.feedback ALTER COLUMN message_id SET NOT NULL;" in INTEGRITY_SQL
    assert "DELETE" not in INTEGRITY_SQL.upper().replace("ON DELETE", "")
