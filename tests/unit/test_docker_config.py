"""Static safety checks for the Docker setup (Step 8). Text-based: no Docker or YAML library needed."""
import re

from backend.config import ROOT

COMPOSE = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
DOCKERIGNORE = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
SCHEMA = (ROOT / "docker" / "postgres" / "01_schema.sql").read_text(encoding="utf-8")
SEED = (ROOT / "docker" / "postgres" / "02_seed.sql").read_text(encoding="utf-8")
NGINX = (ROOT / "frontend" / "nginx.conf").read_text(encoding="utf-8")
DOCKERFILE = (ROOT / "Dockerfile").read_text(encoding="utf-8")


def test_build_context_excludes_secrets_and_local_state():
    for entry in (".env", ".env.*", ".venv", "data/index", "data/*.db", "logs", ".git"):
        assert entry in DOCKERIGNORE, entry


def test_no_secrets_baked_into_compose_or_dockerfile():
    for text in (COMPOSE, DOCKERFILE):
        assert not re.search(r"(?i)\bsk-[a-z0-9_-]{16,}", text)
        assert not re.search(r"(?i)(api_key|password)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{8,}", text.replace("${DOCKER_PG_PASSWORD", ""))
    assert COMPOSE.count("${DOCKER_PG_PASSWORD:?") == 2  # required at runtime, no default value


def test_faiss_index_is_mounted_read_only_and_container_db_overrides_local_pg():
    assert "./data/index:/app/data/index:ro" in COMPOSE
    assert "PG_HOST: db" in COMPOSE and "DB_BACKEND: postgresql" in COMPOSE
    assert not re.search(r"^\s*-\s*\"?[0-9.:]*5432:5432", COMPOSE, re.M)  # container DB port not published


def test_services_have_health_based_startup_and_restart_policy():
    assert COMPOSE.count("condition: service_healthy") == 2
    assert COMPOSE.count("restart: unless-stopped") == 3
    assert "HEALTHCHECK" in DOCKERFILE and "/health" in DOCKERFILE


def test_init_sql_creates_all_tables_and_seeds_only_synthetic_reference_data():
    tables = set(re.findall(r"CREATE TABLE public\.(\w+)", SCHEMA))
    assert tables == {"employees", "leave_balances", "assets", "payroll_calendar", "checklist",
                      "checklist_assignments", "tickets", "messages", "feedback", "escalations"}
    seeded = set(re.findall(r"INSERT INTO public\.(\w+)", SEED))
    assert seeded == {"employees", "leave_balances", "assets", "payroll_calendar", "checklist", "checklist_assignments"}
    assert "restrict" not in SCHEMA + SEED  # pg_dump session tokens stripped
    assert set(re.findall(r"[\w.]+@([\w.]+)'", SEED)) == {"example.com"}


def test_nginx_proxies_api_like_the_vite_dev_proxy():
    assert "location /api/" in NGINX and "rewrite ^/api/(.*)$ /$1 break;" in NGINX
    assert "http://backend:8000" in NGINX and "try_files $uri /index.html;" in NGINX


def test_docker_auth_schema_matches_backend_ddl_and_creates_no_accounts():
    from backend.services.auth_schema import POSTGRES_DDL

    sql = (ROOT / "docker" / "postgres" / "03_auth_schema.sql").read_text(encoding="utf-8")
    assert sql == POSTGRES_DDL
    assert "INSERT" not in sql.upper() and "password_hash text NOT NULL" in sql
    assert 'TRUST_PROXY_HEADERS: "true"' in COMPOSE
