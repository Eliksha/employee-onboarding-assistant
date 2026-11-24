"""Readiness checks for GET /ready (container platforms, App Service health check, deployment verification).

`/health` stays a cheap liveness + database probe. `/ready` answers "can this instance serve every feature?":

* database       - SELECT 1 with short timeouts (same probe as /health)
* schema         - PostgreSQL startup checks: TLS settings, migrations 004/007/008, least-privilege role
* index          - the active FAISS index version loads (read-only) and holds chunks
* embedding_model - the baked-in embedding model loads offline and embeds a probe string
* configuration  - required settings are present for this APP_ENV (names reported in the log only)

The response contains only component names and ok/unavailable: no versions, paths, hosts or setting values.
Successful index and model checks are cached for READY_CACHE_SECONDS so frequent probes stay cheap.
"""
import logging
import threading
import time
from typing import Dict, List

from backend.config import settings

logger = logging.getLogger("app")
READY_CACHE_SECONDS = 60
_cache: Dict[str, float] = {}
_lock = threading.Lock()


def configuration_problems() -> List[str]:
    """Missing or unsafe settings (names only, never values)."""
    from backend.services import llm, postgres

    problems = []
    if not (settings.azure_openai_endpoint.strip() and settings.azure_openai_deployment.strip()
            and settings.azure_openai_api_key.strip()):
        problems.append("AZURE_OPENAI_ENDPOINT/AZURE_OPENAI_DEPLOYMENT/AZURE_OPENAI_API_KEY not all set")
    else:
        try:
            llm.normalize_base_url(settings.azure_openai_endpoint)
        except Exception:
            problems.append("AZURE_OPENAI_ENDPOINT is invalid")
    production = settings.app_env.strip().lower() == "production"
    if settings.db_backend.strip().lower() == "postgresql":
        problems += postgres.tls_problems()
        if production and not settings.pg_reader_user.strip():
            problems.append("PG_READER_USER is required in production")
    elif production:
        problems.append("DB_BACKEND=postgresql is required in production")
    if production:
        if settings.session_cookie_secure.strip().lower() in ("false", "0", "no"):
            problems.append("SESSION_COOKIE_SECURE must not be false in production")
        if not settings.trust_proxy_headers:
            problems.append("TRUST_PROXY_HEADERS must be true behind the platform proxy in production")
        if len(settings.backend_proxy_secret) < 32:
            problems.append("BACKEND_PROXY_SECRET (at least 32 characters) is required in production")
    return problems


def _cached(name: str) -> bool:
    with _lock:
        return time.monotonic() - _cache.get(name, -1e9) < READY_CACHE_SECONDS


def _mark(name: str) -> None:
    with _lock:
        _cache[name] = time.monotonic()


def reset_cache() -> None:
    with _lock:
        _cache.clear()


def _check_schema() -> bool:
    from backend.services import db

    if settings.db_backend.strip().lower() != "postgresql":
        return True
    db.init_db()  # raises with a precise message (logged by the caller) when a check fails
    return True


def _check_index() -> bool:
    if _cached("index"):
        return True
    from backend.services import retriever

    retriever.ensure_loaded()
    if retriever.chunk_count() <= 0:
        raise RuntimeError("the active index holds no chunks")
    _mark("index")
    return True


def _check_model() -> bool:
    if _cached("embedding_model"):
        return True
    from backend.services import embeddings

    vectors = embeddings.embed_texts(["readiness probe"])
    if vectors.shape[0] != 1 or vectors.shape[1] < 64:
        raise RuntimeError("unexpected embedding shape")
    _mark("embedding_model")
    return True


def check() -> Dict[str, str]:
    """Component -> 'ok' | 'unavailable'. Failures are logged with the exception type / setting names only."""
    from backend.services import db

    results: Dict[str, str] = {"database": "ok" if db.check_database() else "unavailable"}
    for name, probe in (("schema", _check_schema), ("index", _check_index), ("embedding_model", _check_model)):
        if name == "schema" and results["database"] != "ok":
            results[name] = "unavailable"
            continue
        try:
            results[name] = "ok" if probe() else "unavailable"
        except Exception as exc:  # details stay in the log; the response has no paths, hosts or versions
            logger.warning("readiness: %s unavailable (%s: %s)", name, type(exc).__name__, str(exc)[:200])
            results[name] = "unavailable"
    problems = configuration_problems()
    if problems:
        logger.warning("readiness: configuration problems: %s", "; ".join(problems))
    results["configuration"] = "unavailable" if problems else "ok"
    return results
