from fastapi import APIRouter, HTTPException

from backend.schemas.models import EscalateRequest, FeedbackRequest, StatusResponse
from backend.services import db

router = APIRouter()


@router.post("/feedback", response_model=StatusResponse)
def feedback(body: FeedbackRequest):
    if not db.message_exists(body.message_id):
        raise HTTPException(status_code=404, detail="Message not found")
    return {"status": "saved", "id": db.add_feedback(body.message_id, body.rating, body.comment)}


@router.post("/escalate", response_model=StatusResponse)
def escalate(body: EscalateRequest):
    return {"status": "escalated to HR/IT (simulated)", "id": db.add_escalation(body.question, body.contact_pref)}
