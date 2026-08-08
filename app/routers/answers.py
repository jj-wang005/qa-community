from fastapi import APIRouter, Path, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.base import get_db
from app.models import User, Question, Answer
from app.schemas.answers import AnswerOut, AnswerCreate

router = APIRouter(prefix="/questions", tags=["回答"])

@router.post("/{question_id}/answers", response_model=AnswerOut)
async def create_answer(
        payload: AnswerCreate,
        question_id: int = Path(..., gt=0),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    existing = db.get(Question, question_id)
    if not existing:
        raise HTTPException(status_code=404, detail="帖子不存在")
    answer = Answer(
        author_id=current_user.id,
        content=payload.content,
        question_id=question_id,
        like_count=0,
        is_accepted=False,
    )

    existing.answer_count += 1
    db.add(answer)
    db.commit()
    author = db.get(User, answer.author_id)
    return {
        "id": answer.id,
        "question_id": answer.question_id,
        "author_name": author.username if author else "未知用户",
        "content": answer.content,
        "like_count": answer.like_count,
        "is_accepted": answer.is_accepted,
        "created_at": answer.created_at,
    }

