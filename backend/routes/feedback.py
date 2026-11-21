"""Answer feedback and HR/IT escalation (authenticated, CSRF-protected)."""
from fastapi import APIRouter, Depends, HTTPException

from backend.schemas.models import EscalateRequest, FeedbackRequest, StatusResponse
from backend.security import FORBIDDEN_OTHER_EMPLOYEE, csrf_protected
from backend.services import db
from backend.services.auth import AuthUser

router = APIRouter()


@router.post("/feedback", response_model=StatusResponse)
def feedback(body: FeedbackRequest, user: AuthUser = Depends(csrf_protected)):
    exists, owner = db.get_message_owner(body.message_id)
    if not exists:
        raise HTTPException(status_code=404, detail="Message not found")
    # Employees may rate only their own messages; legacy messages without an owner are admin-only.
    allowed = owner == user.employee_id if owner is not None else user.role == "admin"
    if not allowed:
        raise HTTPException(status_code=403, detail=FORBIDDEN_OTHER_EMPLOYEE)
    return {"status": "saved", "id": db.add_feedback(body.message_id, body.rating, body.comment)}


@router.post("/escalate", response_model=StatusResponse)
def escalate(body: EscalateRequest, _user: AuthUser = Depends(csrf_protected)):
    return {"status": "escalated to HR/IT (simulated)", "id": db.add_escalation(body.question, body.contact_pref)}
