from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.base import get_db
from app.models import User, Question
from app.schemas.question import CreateQuestion

router = APIRouter(prefix="/questions", tags=["问题"])

@router.post("")
async def create_question(
        payload: CreateQuestion,
        db:Session = Depends(get_db),
        current_user:User = Depends(get_current_user)
):
    question = Question(author_id = current_user.id, title = payload.title, content=payload.content)
    db.add(question)
    db.commit()

    return {"msg": "成功发布"}