from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """All configuration comes from environment variables / the local .env file."""

    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore", protected_namespaces=())

    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    model_name: str = "qwen/qwen3.8-27b"
    embed_model: str = "BAAI/bge-small-en-v1.5"
    similarity_threshold: float = 0.55
    top_k: int = 4
    chunk_words: int = 350
    chunk_overlap_words: int = 40

    raw_dir: Path = ROOT / "data" / "raw"
    index_dir: Path = ROOT / "data" / "index"
    db_path: Path = ROOT / "data" / "app.db"


settings = Settings()
