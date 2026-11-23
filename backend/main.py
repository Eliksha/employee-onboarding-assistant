from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from backend import middleware
from backend.logging_config import setup_logging
from backend.routes import admin, auth, chat, checklist, employees, feedback
from backend.services import db


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    db.init_db()
    yield


def docs_enabled() -> bool:
    """API documentation is served only in development (or when API_DOCS explicitly enables it)."""
    from backend.config import settings

    if settings.api_docs is not None:
        return settings.api_docs
    return settings.app_env.strip().lower() == "development"


_DOCS = docs_enabled()
app = FastAPI(title="Employee Onboarding Assistant", lifespan=lifespan,
              docs_url="/docs" if _DOCS else None, redoc_url="/redoc" if _DOCS else None,
              openapi_url="/openapi.json" if _DOCS else None)
middleware.install(app)

app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(checklist.router)
app.include_router(feedback.router)
app.include_router(admin.router)
app.include_router(employees.router)


DATABASE_UNAVAILABLE = "Service unavailable: the database is not reachable."


@app.get("/health")
def health():
    """Public readiness check: 200 when the database answers, 503 otherwise (no connection details)."""
    headers = {"Cache-Control": "no-store"}
    if db.check_database():
        return JSONResponse({"status": "ok", "database": "ok"}, headers=headers)
    return JSONResponse(
        status_code=503,
        content={"status": "unavailable", "database": "unavailable", "detail": DATABASE_UNAVAILABLE},
        headers=headers,
    )
