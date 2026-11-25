# OnboardAI backend - production image for Azure App Service (Linux, custom container).
#
# Build from the repository root (BuildKit uses deploy/azure/backend.Dockerfile.dockerignore):
#   docker build -f deploy/azure/backend.Dockerfile -t onboardai-backend:<tag> .
#
# Self-contained: the approved handbook PDF/FAQ, the ACTIVE versioned FAISS index and the embedding model are
# baked in and verified at build time, so the container needs no bind mount, no model download and no local
# path. Read-only at runtime: code, documents and index are owned by root; the app user can write only /app/logs.
# No secrets, database dumps or employee records are copied (see the ignore file); every secret is an App Service
# application setting supplied at runtime.
FROM python:3.12-slim

# Security updates of the base image packages (applied at build time; rebuild regularly).
RUN apt-get update && apt-get upgrade -y --no-install-recommends && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    FASTEMBED_CACHE_PATH=/opt/fastembed-cache

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt && pip check

# Embedding model (downloaded once at build time; the runtime is offline: HF_HUB_OFFLINE=1 below).
ARG EMBED_MODEL=BAAI/bge-small-en-v1.5
RUN python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='${EMBED_MODEL}')" \
    && chmod -R a+rX,a-w /opt/fastembed-cache

COPY backend ./backend
COPY data/raw ./data/raw
# Only the approved, active index version (ACTIVE pointer + versions/); never rebuilt in the container.
COPY data/index/ACTIVE ./data/index/ACTIVE
COPY data/index/versions ./data/index/versions

# Production defaults (non-secret). Secrets and environment-specific values are App Service settings.
ENV HF_HUB_OFFLINE=1 \
    APP_ENV=production \
    API_DOCS=false \
    DB_BACKEND=postgresql \
    PG_SSLMODE=verify-full \
    PG_SSLROOTCERT=/etc/ssl/certs/ca-certificates.crt \
    TRUST_PROXY_HEADERS=true \
    SESSION_COOKIE_SECURE=true \
    LOGIN_RATE_LIMIT_BACKEND=database \
    ALLOW_PRIVILEGED_DB_CONNECTION=false \
    EMBED_MODEL=${EMBED_MODEL}

# Build-time verification: index loads offline, matches the bundled documents and the embedding model; the CA
# bundle trusts the roots used by Azure Database for PostgreSQL; no stray secrets or dumps are in the image.
RUN python - <<'PY'
import hashlib, os, pathlib, ssl
from backend.services import embeddings, ingest
version, index, chunks, manifest = ingest.load_active()
assert index.ntotal == len(chunks) == manifest["n_chunks"] > 0, "index/chunk count mismatch"
assert manifest["embed_model"] == os.environ["EMBED_MODEL"], "index built with a different embedding model"
for doc in manifest["documents"]:
    digest = hashlib.sha256(pathlib.Path("data/raw", doc["file"]).read_bytes()).hexdigest()
    assert digest == doc["sha256"], f"{doc['file']} differs from the indexed version"
assert embeddings.embed_texts(["build check"]).shape == (1, manifest["dim"]), "embedding model unusable offline"
ctx = ssl.create_default_context(cafile="/etc/ssl/certs/ca-certificates.crt")
subjects = {dict(x[0] for x in c["subject"]).get("commonName", "") for c in ctx.get_ca_certs()}
for root in ("DigiCert Global Root G2", "Microsoft RSA Root Certificate Authority 2017", "DigiCert Global Root CA"):
    assert root in subjects, f"CA bundle lacks {root}"
bad = [str(p) for p in pathlib.Path("/app").rglob("*") if p.is_file() and (p.suffix in {".env", ".dump", ".db", ".sql", ".pem", ".key"} or p.name.startswith(".env"))]
assert not bad, f"unexpected files in image: {bad}"
print(f"verified: index {version} ({len(chunks)} chunks), model {manifest['embed_model']}, CA bundle OK")
PY

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/logs \
    && chown appuser:appuser /app/logs \
    && chmod -R a-w /app/backend /app/data
USER appuser

EXPOSE 8000
# Container liveness for local runs; App Service uses its own health check on /ready (see deploy/azure/README.md).
HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=5 \
    CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header", "--timeout-keep-alive", "75"]
