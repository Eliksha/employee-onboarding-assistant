from fastapi import APIRouter, HTTPException

from backend.schemas.models import ChatRequest, ChatResponse
from backend.services import db, llm, rag

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    try:
        result = rag.answer_question(req.question)
    except llm.LLMUnavailable:
        raise HTTPException(status_code=503, detail="The AI service is temporarily unavailable. Please try again shortly.")
    return {k: result[k] for k in ("message_id", "answer", "sources", "found")}


@router.get("/history")
def history(limit: int = 20):
    return db.recent_messages(max(1, min(limit, 100)))
