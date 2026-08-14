import json
from typing import List

from fastapi import APIRouter, Path, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.core.deps import get_current_user
from app.core.paginate import paginate
from app.core.redis import redis_client
from app.db.base import get_db
from app.models import User, Question, Answer
from app.schemas.answers import AnswerOut, AnswerCreate, AnswerSort

router = APIRouter(prefix="/questions", tags=["回答"])
answer_router = APIRouter(prefix="/answers", tags=["回答"])

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

    redis_client.delete(f"question:{question_id}")
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

@router.get("/{question_id}/answers", response_model=List[AnswerOut])
async def list_answers(
        sort:AnswerSort = AnswerSort.hot,
        question_id: int = Path(..., gt=0, description = "填入帖子id即可获取评论"),
        db: Session = Depends(get_db),
        page: int = Query(1, ge=1, description="页码从1开始"),
        size: int = Query(10, ge=1, le=100, description="每页的内容数量"),
):
    cache_key = f"answers:{sort.value}:{question_id}:{page}:{size}"
    data = redis_client.get(cache_key)
    if data:
        result = json.loads(data)
        return result
    if sort == AnswerSort.new:
        answers = db.query(Answer).options(joinedload(Answer.author)).filter(Answer.question_id == question_id).order_by(Answer.created_at.desc())
        answers = paginate(answers, page, size)
    elif sort == AnswerSort.accepted:
        answers = db.query(Answer).options(joinedload(Answer.author)).filter(Answer.question_id == question_id, Answer.is_accepted ==True).order_by(Answer.like_count.desc())
        answers = paginate(answers, page, size)
    else:
        hot_expr = func.log2(Answer.like_count + 1) * 10 + Answer.is_accepted * 50
        answers = db.query(Answer).options(joinedload(Answer.author)).filter(Answer.question_id == question_id).order_by(hot_expr.desc())
        answers = paginate(answers, page, size)
    cache_body = []
    for q in answers:
        cache_body.append({
            "id": q.id,
            "question_id": q.question_id,
            "author_name": q.author.username if q.author else "未知用户",
            "content": q.content,
            "like_count": q.like_count,
            "is_accepted": q.is_accepted,
            "created_at": q.created_at,
        })

    redis_client.set(cache_key, json.dumps(cache_body, default=str), ex=60)

    return cache_body

@answer_router.post("/{answer_id}/accept")
async def accepte_answers(
        answer_id: int = Path(..., gt=0, description="接受你喜欢的评论"),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    answers = db.get(Answer, answer_id)
    if not answers:
        raise HTTPException(status_code=404, detail="糟糕，评论不见了")
    question = db.get(Question, answers.question_id)
    if question.author_id == current_user.id:
        answers.is_accepted = True
    else:
        raise HTTPException(status_code=403, detail="只有作者才可以采纳评论")
    db.commit()

    for k in redis_client.keys(f"answers:{answers.question_id}:*"):
        redis_client.delete(k)

    return {"接受": answers.is_accepted}
