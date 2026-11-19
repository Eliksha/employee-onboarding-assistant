from typing import List

from fastapi import APIRouter, HTTPException

from backend.schemas.models import ChecklistItem, ChecklistUpdate
from backend.services import db

router = APIRouter()


@router.get("/checklist", response_model=List[ChecklistItem])
def get_checklist():
    return db.get_checklist()


@router.patch("/checklist/{item_id}", response_model=ChecklistItem)
def update_item(item_id: int, body: ChecklistUpdate):
    item = db.set_checklist_done(item_id, body.done)
    if item is None:
        raise HTTPException(status_code=404, detail="Checklist item not found")
    return item
