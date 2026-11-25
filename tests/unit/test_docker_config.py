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


def test_hr_queue_schema_ships_identically_for_fresh_docker_databases():
    from backend.services import hr_queue_schema

    sql = (ROOT / "docker" / "postgres" / "05_hr_queue.sql").read_text(encoding="utf-8")
    assert sql == hr_queue_schema.POSTGRES_DDL
    assert not re.search(r"(?i)\b(INSERT INTO|DELETE FROM|UPDATE \w+ SET|DROP TABLE|TRUNCATE)\b", sql)   # additive only


def test_hr_queue_ddl_splits_into_complete_statements():
    """Regression: a ';' inside a comment must not produce a statement fragment (found in the migration rehearsal)."""
    from backend.services import hr_queue_schema

    statements = hr_queue_schema._statements()
    assert len(statements) == 13   # 4 constraint changes, 3 columns, 2 tables, 4 indexes
    for statement in statements:
        assert statement.split()[0] in ("ALTER", "CREATE"), statement[:60]
        assert "--" not in statement


def test_azure_images_bundle_only_approved_assets_and_no_secrets():
    backend = (ROOT / "deploy" / "azure" / "backend.Dockerfile").read_text(encoding="utf-8")
    ignore = (ROOT / "deploy" / "azure" / "backend.Dockerfile.dockerignore").read_text(encoding="utf-8").splitlines()
    assert ignore[next(i for i, line in enumerate(ignore) if not line.startswith("#"))] == "*"   # allow-list
    for allowed in ("!requirements.txt", "!backend/", "!data/raw/", "!data/index/ACTIVE", "!data/index/versions/"):
        assert allowed in ignore
    for denied in ("**/*.db", "**/*.dump", "**/.env", "**/.env.*"):
        assert denied in ignore
    assert "COPY data/index/ACTIVE" in backend and "COPY data/index/versions" in backend
    for setting in ("APP_ENV=production", "PG_SSLMODE=verify-full", "SESSION_COOKIE_SECURE=true", "API_DOCS=false",
                    "LOGIN_RATE_LIMIT_BACKEND=database", "HF_HUB_OFFLINE=1", "ALLOW_PRIVILEGED_DB_CONNECTION=false"):
        assert setting in backend
    assert "USER appuser" in backend and "chmod -R a-w /app/backend /app/data" in backend
    for text in (backend, (ROOT / "deploy" / "azure" / "frontend.Dockerfile").read_text(encoding="utf-8")):
        assert not re.search(r"(?i)(api_key|password|secret)\s*=\s*['\"]?[A-Za-z0-9_\-]{8,}", text)


def test_azure_nginx_template_keeps_security_headers_and_adds_hsts():
    template = (ROOT / "deploy" / "azure" / "nginx.conf.template").read_text(encoding="utf-8")
    local_csp = re.search(r'Content-Security-Policy "([^"]+)"', NGINX).group(1)
    assert f'Content-Security-Policy "{local_csp}"' in template and "googleapis" not in local_csp
    assert 'Strict-Transport-Security "max-age=31536000; includeSubDomains"' in template
    for directive in ("proxy_ssl_verify on;", "proxy_ssl_server_name on;", "X-OnboardAI-Proxy-Key ${BACKEND_PROXY_SECRET}",
                      "proxy_pass $backend_upstream;", "location = /api/ready", "server_tokens off;"):
        assert directive in template
    assert "backend:8000" not in template and "localhost" not in template   # no compose service names / localhost


# ---------------------------------------------------------------- temporary migration image (App Service SSH tunnel)
MIGRATION = ROOT / "deploy" / "azure" / "migration"


def test_migration_sshd_is_key_only_non_root_and_without_forwarding():
    cfg = {line.split()[0].lower(): " ".join(line.split()[1:]) for line in
           (MIGRATION / "sshd_config").read_text(encoding="utf-8").splitlines() if line.strip() and not line.startswith("#")}
    assert cfg["port"] == "2222" and cfg["permitrootlogin"] == "no" and cfg["allowusers"] == "appuser"
    assert cfg["authenticationmethods"] == "publickey" and cfg["passwordauthentication"] == "no"
    assert cfg["kbdinteractiveauthentication"] == "no" and cfg["pubkeyacceptedalgorithms"] == "ssh-ed25519"
    for option in ("allowtcpforwarding", "allowagentforwarding", "allowstreamlocalforwarding", "x11forwarding",
                   "permittunnel", "gatewayports", "permituserenvironment"):
        assert cfg[option] == "no", option


def test_migration_entrypoint_requires_one_ed25519_key_and_drops_privileges():
    entry = (MIGRATION / "migration-entrypoint.sh").read_text(encoding="utf-8")
    assert r"ssh-ed25519\ *) ;;" in entry and "exactly one public key" in entry
    assert "rm -f /etc/ssh/ssh_host_*" in entry and "ssh-keygen -q -t ed25519" in entry   # fresh host key per start
    assert "exec setpriv --reuid=10001 --regid=10001" in entry and "uvicorn" not in entry  # app not started
    dockerfile = (MIGRATION / "migration.Dockerfile").read_text(encoding="utf-8")
    assert "usermod -p '*' appuser" in dockerfile and "rm -f /etc/ssh/ssh_host_*" in dockerfile
    assert not re.search(r"(?i)(chpasswd|Docker!|PermitRootLogin yes)", dockerfile + entry)


def test_production_images_contain_no_ssh_server_or_database_client():
    for name in ("backend.Dockerfile", "frontend.Dockerfile"):
        text = (ROOT / "deploy" / "azure" / name).read_text(encoding="utf-8")
        assert "openssh" not in text and "sshd" not in text and "postgresql-client" not in text, name


def test_in_vnet_migration_refuses_non_empty_targets_verifies_tls_and_rolls_back():
    script = (MIGRATION / "in-vnet-migrate.sh").read_text(encoding="utf-8")
    assert "sslmode=verify-full" in script and "refusing to overwrite existing data" in script
    assert "trap 'log \"error - rolling back\"; rollback; shred_files' ERR" in script
    assert "--single-transaction" in script and "ON_ERROR_STOP=1" in script and "shred -u" in script
    assert 'die "unexpected input key' in script            # only the expected secret names are accepted on stdin
    assert "rollback empties the target database: pass --confirm" in script


def test_azure_scripts_never_open_the_database_to_the_public():
    for path in (ROOT / "deploy" / "azure").glob("*.ps1"):
        if path.name == "Test-DeploymentScripts.ps1":
            continue
        text = path.read_text(encoding="utf-8")
        assert "'firewall-rule', 'create'" not in text and "'--public-access'" not in text, path.name
