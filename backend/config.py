from pathlib import Path

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
    top_k: int = 4
    chunk_words: int = 350
    chunk_overlap_words: int = 40

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


settings = Settings()