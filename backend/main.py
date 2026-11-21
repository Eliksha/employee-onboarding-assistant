from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend import middleware
from backend.logging_config import setup_logging
from backend.routes import admin, auth, chat, checklist, employees, feedback
from backend.services import db


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    db.init_db()
    yield


app = FastAPI(title="Employee Onboarding Assistant", lifespan=lifespan)
middleware.install(app)

app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(checklist.router)
app.include_router(feedback.router)
app.include_router(admin.router)
app.include_router(employees.router)


@app.get("/health")
def health():
    return {"status": "ok"}
