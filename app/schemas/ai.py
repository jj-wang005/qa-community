from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=200)
    session_id: UUID | None = None


class ApprovalDecision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    type: Literal['approve', 'reject']


class ApprovalRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    session_id: UUID
    approval_id: UUID
    decisions: list[ApprovalDecision] = Field(..., min_length=1, max_length=20)
