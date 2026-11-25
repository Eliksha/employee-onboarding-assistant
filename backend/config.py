from pathlib import Path
from typing import Optional

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Configuration from environment variables and the local .env file."""

    model_config = SettingsConfigDict(
        env_file=ROOT / ".env",
        extra="ignore",
        protected_namespaces=(),
    )

    # LLM: Azure OpenAI (GPT-4.1 deployment) through the OpenAI v1 Responses API (backend/services/llm.py).
    # The endpoint is the resource's v1 base URL (https://<resource>.services.ai.azure.com/openai/v1); the bare
    # resource URL is also accepted and normalised. AZURE_OPENAI_BASE_URL is accepted as an alias.
    azure_openai_endpoint: str = Field("", validation_alias=AliasChoices("AZURE_OPENAI_ENDPOINT",
                                                                         "AZURE_OPENAI_BASE_URL"))
    azure_openai_deployment: str = ""
    azure_openai_api_key: str = ""
    llm_timeout_seconds: float = 30.0
    llm_max_retries: int = 2
    llm_max_output_tokens: int = 600

    # RAG
    embed_model: str = "BAAI/bge-small-en-v1.5"
    similarity_threshold: float = 0.65
    # Scores in [threshold - margin, threshold) reach the LLM only with keyword corroboration.
    borderline_margin: float = 0.05
    top_k: int = 4
    chunk_words: int = 350
    chunk_overlap_words: int = 40

    # Authentication and sessions
    app_env: str = "development"            # "production" blocks the dev account-provisioning CLI
    api_docs: Optional[bool] = None         # /docs, /redoc, /openapi.json; default: only when app_env=development
    session_cookie_name: str = "onboardai_session"
    session_cookie_secure: str = "auto"     # auto | true | false ("auto" = Secure when the request is HTTPS)
    session_ttl_minutes: int = 480          # absolute lifetime of a session
    session_idle_minutes: int = 60          # inactivity timeout
    trust_proxy_headers: bool = False       # honour X-Forwarded-For/-Proto (enable only behind a trusted proxy)
    # Number of trusted proxies that each append one entry to X-Forwarded-For in front of the backend.
    # Local Docker: 1 (nginx). Azure App Service: see deploy/azure/README.md (verified after deployment).
    trusted_proxy_hops: int = 1
    # Shared secret the frontend proxy adds as X-OnboardAI-Proxy-Key; when set, the backend rejects every
    # request without it (except /health and /ready), so the backend is not usable directly.
    backend_proxy_secret: str = ""
    login_max_failures_per_email: int = 5
    login_max_failures_per_ip: int = 20
    login_window_seconds: int = 900
    # "auto": shared PostgreSQL table when DB_BACKEND=postgresql (safe across workers and replicas),
    # in-process memory otherwise. "memory" / "database" force one of them.
    login_rate_limit_backend: str = "auto"
    login_rate_limit_max_keys: int = 10000  # bound on tracked keys for the in-memory limiter
    password_min_length: int = 12

    # File paths
    raw_dir: Path = ROOT / "data" / "raw"
    index_dir: Path = ROOT / "data" / "index"
    db_path: Path = ROOT / "data" / "app.db"
    log_dir: Path = ROOT / "logs"

    # Database configuration
    db_backend: str = "sqlite"
    pg_host: str = "localhost"
    pg_port: int = 5432
    pg_database: str = "onboardai"
    pg_user: str = "postgres"
    pg_password: str = ""
    # /health database probe: short connect + statement timeout (seconds) so a dead DB never hangs it.
    # libpq treats connect timeouts below 2 s as 2 s.
    health_db_timeout_seconds: int = 3
    # Server-side statement timeout for application (read-write) connections; 0 disables it.
    pg_statement_timeout_ms: int = 10000
    # TLS: libpq sslmode (disable | allow | prefer | require | verify-ca | verify-full). APP_ENV=production
    # requires verify-full (certificate chain AND host name checked). PG_SSLROOTCERT is the CA bundle; the
    # backend image ships the Debian CA bundle at /etc/ssl/certs/ca-certificates.crt.
    pg_sslmode: str = "prefer"
    pg_sslrootcert: str = ""
    # Bounded connection pool (per credential set). Connections are validated before reuse, recycled after
    # PG_POOL_MAX_LIFETIME_SECONDS, discarded after connection errors, and reset (ROLLBACK + DISCARD ALL)
    # when returned, so no transaction, session setting or employee scope survives into the next request.
    pg_pool_enabled: bool = True
    pg_pool_max_size: int = 5      # per credential set and instance; keep instances x size within the role CONNECTION LIMITs (app 20, reader 10)
    pg_pool_timeout_seconds: float = 5.0
    pg_pool_max_lifetime_seconds: int = 1800
    pg_pool_validate_idle_seconds: float = 5.0
    # The app refuses to start as a superuser/BYPASSRLS role. Local-development escape hatch only: honoured
    # solely with APP_ENV=development; docker-compose.yml pins it to false.
    allow_privileged_db_connection: bool = False

    # SQL-agent / read-only data access (see backend/services/readonly_query.py).
    # PG_READER_USER is the least-privilege SELECT-only role created by
    # backend/migrations/005_least_privilege_roles.py. When it is empty, read-only queries fall back to
    # the application credentials, still inside READ ONLY transactions with the timeout and row limit.
    pg_reader_user: str = ""
    pg_reader_password: str = ""
    # HMAC secret for the signed employee scope checked by row-level security (same value that
    # migration 005 stored in onboardai_private.scope_key). Required when PG_READER_USER is set.
    pg_scope_secret: str = ""
    sql_agent_statement_timeout_ms: int = 5000
    sql_agent_max_rows: int = 200


settings = Settings()