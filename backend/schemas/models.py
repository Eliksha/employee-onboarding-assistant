
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    question: str = Field(..., max_length=500)
    employee_id: Optional[str] = None

    @field_validator("question")
    @classmethod
    def not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Question must not be empty")
        return v


class Source(BaseModel):
    file: str
    section: str
    score: float
    page: Optional[int] = None  # PDF page of a handbook passage (optional; omitted when not applicable)


class ChatResponse(BaseModel):
    message_id: int
    answer: str
    sources: List[Source]
    found: bool


class ChecklistItem(BaseModel):
    id: int
    phase: str
    task: str
    done: bool


class ChecklistUpdate(BaseModel):
    done: bool


class FeedbackRequest(BaseModel):
    message_id: int
    rating: Literal["up", "down"]
    comment: Optional[str] = Field(default=None, max_length=500)


class EscalateRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)
    contact_pref: Optional[str] = Field(default=None, max_length=100)
    message_id: Optional[int] = None  # optional: the chat answer being escalated (must be the caller's own)


class StatusResponse(BaseModel):
    status: str
    id: Optional[int] = None
