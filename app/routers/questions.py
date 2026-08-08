from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.base import get_db
from app.models import User, Question
from app.schemas.questions import CreateQuestion, QuestionOut

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

@router.get("")
async def list_questions(db: Session = Depends(get_db)):
    questions = db.query(Question).order_by(Question.created_at.desc()).all()
    result=[]
    for q in questions:
        author = db.get(User,q.author_id)
        result.append({
            "id": q.id,
            "author_name": author.username if author else "未知用户",
            "title": q.title,
            "content": q.content,
            "answer_count": q.answer_count,
            "view_count": q.view_count,
            "created_at": q.created_at,
            "updated_at": q.updated_at,
        })

    return result

@router.get("/{id}")
async def get_questions(id:int = Path(...,gt = 0, description="填写想要查询的新闻id"),
                        db: Session = Depends(get_db)
                        ):
    existing = db.get(Question,id)
    if not existing:
        raise HTTPException(status_code=404, detail="内容不存在")
    existing.view_count += 1
    db.commit()
    author = db.get(User,existing.author_id)
    return{
        "id": existing.id,
        "author_name": author.username if author else "未知用户",
        "title": existing.title,
        "content": existing.content,
        "answer_count": existing.answer_count,
        "view_count": existing.view_count,
        "created_at": existing.created_at,
        "updated_at": existing.updated_at,
    }
