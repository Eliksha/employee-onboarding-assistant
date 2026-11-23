
"""Chat endpoints for handbook RAG and employee-specific queries.

Authorization: the employee is always the signed-in user's own employee (from the session).
A body/query `employee_id` is accepted for compatibility but must match the session (403 otherwise).
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.schemas.models import ChatRequest, ChatResponse
from backend.security import assert_own_employee, csrf_protected, current_user
from backend.services.auth import AuthUser
from backend.services import db, llm, orchestrator
from backend.services.employee_db import UnknownEmployeeError, get_employee


router = APIRouter()
logger = logging.getLogger("app")


@router.post("/chat", response_model=ChatResponse, response_model_exclude_none=True)
def chat(req: ChatRequest, user: AuthUser = Depends(csrf_protected)):
    """Answer handbook or employee-specific questions for the signed-in user."""

    if user.employee_id is not None:
        employee_id = assert_own_employee(user, req.employee_id)
        if get_employee(employee_id) is None:
            raise HTTPException(
                status_code=404,
                detail="Employee not found.",
            )
    elif req.employee_id is not None:
        # Accounts without an employee workspace (admins) cannot act as an employee.
        assert_own_employee(user, req.employee_id)
    else:
        employee_id = None

    try:
        result = orchestrator.answer_question(
            question=req.question,
            employee_id=employee_id,
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
    employee_id: Optional[str] = Query(
        default=None,
        description="Optional; must equal the signed-in employee (defaults to it)",
    ),
    limit: int = Query(default=20, ge=1, le=100),
    user: AuthUser = Depends(current_user),
):
    """Return the signed-in employee's own chat history."""

    employee_id = assert_own_employee(user, employee_id)
    if get_employee(employee_id) is None:
        raise HTTPException(
            status_code=404,
            detail="Employee not found.",
        )

    return db.recent_employee_messages(
        employee_id=employee_id,
        limit=limit,
    )
