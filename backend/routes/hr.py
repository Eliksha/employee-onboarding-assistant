"""HR/IT support escalation queue (role `hr` only; writes need the session's CSRF token).

Escalations raised from the chat land here. HR/IT staff can list them, open one (each opening is recorded in
the escalation's audit trail) and move it through open -> in_progress -> resolved -> closed with an optional
note that the employee's chat history then reflects as the escalation status. Employees and administrators
get 403. Responses are never cached.
"""
import logging
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field

from backend.security import require_hr, require_hr_write
from backend.services import db, hr_queue_schema
from backend.services.auth import AuthUser

router = APIRouter(prefix="/hr", tags=["HR/IT escalation queue"])
logger = logging.getLogger("app")

Status = Literal["open", "in_progress", "resolved", "closed"]


class EscalationUpdate(BaseModel):
    status: Status
    note: Optional[str] = Field(default=None, max_length=hr_queue_schema.NOTE_MAX_LENGTH)


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


@router.get("/escalations")
def list_escalations(response: Response, status: Optional[Status] = Query(default=None),
                     limit: int = Query(default=100, ge=1, le=200), user: AuthUser = Depends(require_hr)):
    _no_store(response)
    items = db.list_escalations(status=status, limit=limit)
    logger.info("hr queue listed user_id=%s status=%s count=%d", user.user_id, status or "all", len(items))
    return {"items": items, "transitions": {k: list(v) for k, v in hr_queue_schema.ESCALATION_TRANSITIONS.items()}}


@router.get("/escalations/{escalation_id}")
def get_escalation(escalation_id: int, response: Response, user: AuthUser = Depends(require_hr)):
    _no_store(response)
    try:
        item = db.get_escalation(escalation_id, viewer_user_id=user.user_id)
    except db.EscalationNotFound:
        raise HTTPException(status_code=404, detail="Escalation not found")
    logger.info("hr escalation viewed id=%s user_id=%s", escalation_id, user.user_id)
    return item


@router.patch("/escalations/{escalation_id}")
def update_escalation(escalation_id: int, body: EscalationUpdate, response: Response,
                      user: AuthUser = Depends(require_hr_write)):
    _no_store(response)
    try:
        item = db.update_escalation_status(escalation_id, body.status, user.user_id, body.note)
    except db.EscalationNotFound:
        raise HTTPException(status_code=404, detail="Escalation not found")
    except db.InvalidTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    logger.info("hr escalation status changed id=%s to=%s user_id=%s", escalation_id, body.status, user.user_id)
    return item
