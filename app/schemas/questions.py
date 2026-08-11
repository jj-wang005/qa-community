from enum import Enum

from pydantic import BaseModel, Field
from datetime import datetime
class CreateQuestion(BaseModel):
    title: str = Field(min_length=1, max_length = 200, description = "此条用于输入标题")
    content: str = Field(min_length=1, max_length = 1000, description = "此条用于输入内容")

class QuestionOut(BaseModel):
    id: int
    author_name: str
    title: str
    content: str
    answer_count: int
    view_count: int
    created_at: datetime
    updated_at: datetime

class QuestionSort(str, Enum):
    hot = "hot"
    new = "new"