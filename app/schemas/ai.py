from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(..., max_length = 200)
    session_id: str | None = None