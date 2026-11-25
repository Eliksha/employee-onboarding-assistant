"""Answer feedback and HR/IT escalation (authenticated, CSRF-protected)."""
from fastapi import APIRouter, Depends, HTTPException

from backend.schemas.models import EscalateRequest, FeedbackRequest, StatusResponse
from backend.security import FORBIDDEN_OTHER_EMPLOYEE, csrf_protected
from backend.services import db
from backend.services.auth import AuthUser

router = APIRouter()


def _assert_own_message(message_id: int, user: AuthUser) -> None:
    exists, owner = db.get_message_owner(message_id)
    if not exists:
        raise HTTPException(status_code=404, detail="Message not found")
    # Employees may act only on their own messages; legacy messages without an owner are admin-only.
    allowed = owner == user.employee_id if owner is not None else user.role == "admin"
    if not allowed:
        raise HTTPException(status_code=403, detail=FORBIDDEN_OTHER_EMPLOYEE)


@router.post("/feedback", response_model=StatusResponse)
def feedback(body: FeedbackRequest, user: AuthUser = Depends(csrf_protected)):
    _assert_own_message(body.message_id, user)
    return {"status": "saved", "id": db.add_feedback(body.message_id, body.rating, body.comment)}


@router.post("/escalate", response_model=StatusResponse)
def escalate(body: EscalateRequest, user: AuthUser = Depends(csrf_protected)):
    """Put a question in the HR/IT support queue (GET /hr/escalations), attributed to the signed-in employee;
    optionally for one chat answer. Delivery is in-app only: no e-mail or ticketing integration."""
    if body.message_id is not None:
        _assert_own_message(body.message_id, user)
        existing = db.find_escalation(body.message_id)
        if existing is not None:
            return {"status": "already in the HR/IT support queue", "id": existing}
    escalation_id = db.add_escalation(body.question, body.contact_pref, employee_id=user.employee_id,
                                      message_id=body.message_id, actor_user_id=user.user_id)
    return {"status": "sent to the HR/IT support queue", "id": escalation_id}
