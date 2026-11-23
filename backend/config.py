from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Configuration from environment variables and the local .env file."""

    model_config = SettingsConfigDict(
        env_file=ROOT / ".env",
        extra="ignore",
        protected_namespaces=(),
    )

    # LLM and RAG
    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    model_name: str = "qwen/qwen3.8-27b"
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
    login_max_failures_per_email: int = 5
    login_max_failures_per_ip: int = 20
    login_window_seconds: int = 900
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