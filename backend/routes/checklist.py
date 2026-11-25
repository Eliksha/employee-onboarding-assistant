from typing import List

"""Legacy shared checklist (not per employee): administrator-only."""
from fastapi import APIRouter, Depends, HTTPException

from backend.schemas.models import ChecklistItem, ChecklistUpdate
from backend.security import require_admin, require_admin_write
from backend.services import db

router = APIRouter()


@router.get("/checklist", response_model=List[ChecklistItem], dependencies=[Depends(require_admin)])
def get_checklist():
    return db.get_checklist()


@router.patch("/checklist/{item_id}", response_model=ChecklistItem, dependencies=[Depends(require_admin_write)])
def update_item(item_id: int, body: ChecklistUpdate):
    item = db.set_checklist_done(item_id, body.done)
    if item is None:
        raise HTTPException(status_code=404, detail="Checklist item not found")
    return item
