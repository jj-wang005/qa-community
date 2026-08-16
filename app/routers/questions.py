import json
from typing import List

import redis
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.core.deps import get_current_user
from app.core.paginate import paginate
from app.core.redis import redis_client
from app.db.base import get_db
from app.models import User, Question
from app.schemas.questions import CreateQuestion, QuestionOut, QuestionSort

router = APIRouter(prefix="/questions", tags=["问题"])

@router.post("")
def create_question(
        payload: CreateQuestion,
        db:Session = Depends(get_db),
        current_user:User = Depends(get_current_user)
):

    question = Question(author_id = current_user.id, title = payload.title, content=payload.content)
    db.add(question)
    db.commit()

    for k in redis_client.scan_iter("questions:new:*"):
        redis_client.delete(k)

    return {"msg": "成功发布"}

@router.get("",  response_model=List[QuestionOut])
def list_questions(
        sort: QuestionSort = QuestionSort.hot,
        db: Session = Depends(get_db),
        page: int = Query(1,ge=1,description="页码从1开始"),
        size: int = Query(10,ge=1,le=100, description="每页的内容数量"),
):
    key = f"questions:{sort.value}:{page}:{size}"
    data = redis_client.get(key)
    if data:
        # print("【命中缓存】不用查库了")
        return json.loads(data)

    if sort == QuestionSort.new:
        questions = db.query(Question).options(joinedload(Question.author)).order_by(Question.created_at.desc())
        questions = paginate(questions, page, size)
    else:
        hot_expr = func.log2(Question.view_count + 1) + Question.answer_count * 10
        questions = db.query(Question).options(joinedload(Question.author)).order_by(hot_expr.desc())
        questions = paginate(questions, page, size)
        # 在原表的基础上进行修改，sort返回值是none
        # questions = db.query(Question).all()
        # all_questions = sorted(questions, key = lambda q:q.hot_score(), reverse=True)
        # questions = all_questions[offset: offset + size]
        # 重新复制给新的表，sorted返回值是一个新的列表
        # questions = questions.sorted(key = lambda q:q.hot_score(), reverse=True)
    result=[]
    for q in questions:
        result.append({
            "id": q.id,
            "author_name": q.author.username if q.author else "未知用户",
            "title": q.title,
            "content": q.content,
            "answer_count": q.answer_count,
            "view_count": q.view_count,
            "created_at": q.created_at,
            "updated_at": q.updated_at,
        })
    redis_client.set(key, json.dumps(result, default=str), ex=60)
    # print("【未命中】查了数据库")
    return result

@router.get("/{id}",  response_model=QuestionOut)
def get_questions(id:int = Path(...,gt = 0, description="填写想要查询的新闻id"),
                        db: Session = Depends(get_db)
                        ):

    cache_key = f"question:{id}"
    data = redis_client.get(cache_key)
    if data:
        view_count = redis_client.incr(f"question:views:{id}")  # incr等于increment
        result = json.loads(data)
        result["view_count"] = view_count
        return result
    existing = db.query(Question).options(joinedload(Question.author)).filter(Question.id == id).first()
    if not existing:
        raise HTTPException(status_code=404, detail="内容不存在")
    redis_client.set(f"question:views:{id}", value=existing.view_count, nx=True)
    view_count = redis_client.incr(f"question:views:{id}") # incr等于increment
    cache_body = {
        "id": existing.id,
        "author_name": existing.author.username if existing.author else "未知用户",
        "title": existing.title,
        "content": existing.content,
        "answer_count": existing.answer_count,
        "created_at": existing.created_at,
        "updated_at": existing.updated_at,
    }

    redis_client.set(cache_key, json.dumps(cache_body, default=str), ex=60)
    cache_body["view_count"] = view_count
    return cache_body