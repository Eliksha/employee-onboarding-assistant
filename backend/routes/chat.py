
"""Chat endpoints for handbook RAG and employee-specific queries."""

import logging

from fastapi import APIRouter, HTTPException, Query

from backend.schemas.models import ChatRequest, ChatResponse
from backend.services import db, llm, orchestrator
from backend.services.employee_db import UnknownEmployeeError, get_employee


router = APIRouter()
logger = logging.getLogger("app")


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    """Answer handbook or employee-specific questions."""

    # Validate a selected demo employee, if provided.
    if req.employee_id is not None:
        if get_employee(req.employee_id) is None:
            raise HTTPException(
                status_code=404,
                detail="Employee not found.",
            )

    try:
        result = orchestrator.answer_question(
            question=req.question,
            employee_id=req.employee_id,
        )

    except llm.LLMUnavailable as exc:
        logger.warning(
            "LLM unavailable: %s",
            str(exc)[:200],
        )
        raise HTTPException(
            status_code=503,
            detail=(
                "The AI service is temporarily unavailable. "
                "Please try again shortly."
            ),
        )

    except UnknownEmployeeError as exc:
        logger.warning(
            "Chat request rejected: %s",
            str(exc)[:200],
        )
        raise HTTPException(
            status_code=400,
            detail="Invalid employee or query.",
        )

    logger.info(
        "chat answered found=%s top_score=%.3f question_chars=%d",
        result["found"],
        result["top_score"],
        len(req.question),
    )

    return {
        key: result[key]
        for key in (
            "message_id",
            "answer",
            "sources",
            "found",
        )
    }


@router.get("/history")
def history(
    employee_id: str = Query(
        ...,
        description="Selected fictional employee ID",
    ),
    limit: int = Query(default=20, ge=1, le=100),
):
    """Return chat history for the selected demo employee."""

    if get_employee(employee_id) is None:
        raise HTTPException(
            status_code=404,
            detail="Employee not found.",
        )

    return db.recent_employee_messages(
        employee_id=employee_id,
        limit=limit,
    )
