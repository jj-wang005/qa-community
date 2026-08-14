from enum import Enum

from pydantic import BaseModel, Field
from datetime import datetime

class AnswerCreate(BaseModel):
    content: str = Field(...,max_length = 1000,description = "快去发一条评论吧")

class AnswerOut(BaseModel):
    id: int
    question_id: int
    author_name: str
    content: str
    like_count: int
    is_accepted: bool
    created_at: datetime

class AnswerSort(str, Enum):
    hot = "hot"
    new = "new"
    accepted = "accepted"
