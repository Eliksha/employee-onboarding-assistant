from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.routes import admin, chat, checklist, feedback
from backend.services import db


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="Employee Onboarding Assistant", lifespan=lifespan)

app.include_router(chat.router)
app.include_router(checklist.router)
app.include_router(feedback.router)
app.include_router(admin.router)


@app.get("/health")
def health():
    return {"status": "ok"}
