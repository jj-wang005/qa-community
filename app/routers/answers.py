import json
from typing import List

from fastapi import APIRouter, Path, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.core.deps import get_current_user, get_current_user_optional
from app.core.kb_events import enqueue_kb_sync
from app.core.paginate import paginate
from app.core.redis_client import redis_client
from app.db.base import get_db
from app.models import User, Question, Answer, Like
from app.schemas.answers import AnswerOut, AnswerCreate, AnswerSort

router = APIRouter(prefix="/questions", tags=["回答"])
answer_router = APIRouter(prefix="/answers", tags=["回答"])


def _with_like_state(items: list[dict], db: Session, current_user: User | None) -> list[dict]:
    """公共回答内容可共享缓存，当前用户的点赞状态在返回前单独叠加。"""
    liked_ids: set[int] = set()
    if current_user is not None and items:
        answer_ids = [item["id"] for item in items]
        liked_ids = {
            answer_id for (answer_id,) in db.query(Like.answer_id).filter(
                Like.user_id == current_user.id,
                Like.answer_id.in_(answer_ids),
            ).all()
        }
    return [{**item, "is_liked": item["id"] in liked_ids} for item in items]

@router.post("/{question_id}/answers", response_model=AnswerOut)
def create_answer(
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
    enqueue_kb_sync(db, question_id)
    db.commit()

    redis_client.delete(f"question:{question_id}")
    # 回答列表缓存键为 answers:{sort}:{question_id}:{page}:{size}。
    # 发布后必须清理所有排序和分页，否则回答数已增加但列表仍返回旧缓存。
    for key in redis_client.scan_iter(f"answers:*:{question_id}:*"):
        redis_client.delete(key)
    author = db.get(User, answer.author_id)
    return {
        "id": answer.id,
        "question_id": answer.question_id,
        "author_name": author.username if author else "未知用户",
        "content": answer.content,
        "like_count": answer.like_count,
        "is_accepted": answer.is_accepted,
        "is_liked": False,
        "created_at": answer.created_at,
    }

@router.get("/{question_id}/answers", response_model=List[AnswerOut])
def list_answers(
        sort:AnswerSort = AnswerSort.hot,
        question_id: int = Path(..., gt=0, description = "填入帖子id即可获取评论"),
        db: Session = Depends(get_db),
        page: int = Query(1, ge=1, description="页码从1开始"),
        size: int = Query(10, ge=1, le=100, description="每页的内容数量"),
        current_user: User | None = Depends(get_current_user_optional),
):
    cache_key = f"answers:{sort.value}:{question_id}:{page}:{size}"
    data = redis_client.get(cache_key)
    if data:
        result = json.loads(data)
        return _with_like_state(result, db, current_user)
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

    return _with_like_state(cache_body, db, current_user)

@answer_router.post("/{answer_id}/accept")
def accepte_answers(
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
    enqueue_kb_sync(db, answers.question_id)
    db.commit()

    for k in redis_client.scan_iter(f"answers:*:{answers.question_id}:*"):
        redis_client.delete(k)

    return {"接受": answers.is_accepted}


@answer_router.delete("/{answer_id}")
def delete_answer(
        answer_id: int = Path(..., gt=0),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    answer = db.get(Answer, answer_id)
    if not answer:
        raise HTTPException(status_code=404, detail="糟糕，评论不见了")
    if answer.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="只有作者才可以删除回答")

    question_id = answer.question_id
    question = db.get(Question, question_id)
    if question:
        question.answer_count = max(0, question.answer_count - 1)
    enqueue_kb_sync(db, question_id)
    db.delete(answer)
    db.commit()

    redis_client.delete(f"question:{question_id}")
    for key in redis_client.scan_iter(f"answers:*:{question_id}:*"):
        redis_client.delete(key)
    for key in redis_client.scan_iter("questions:*"):
        redis_client.delete(key)

    return {"msg": "删除成功"}
