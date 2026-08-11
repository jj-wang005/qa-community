import json
from typing import List

import redis
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.paginate import paginate
from app.core.redis import redis_client
from app.db.base import get_db
from app.models import User, Question
from app.schemas.questions import CreateQuestion, QuestionOut, QuestionSort

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

    for k in redis_client.keys("questions:new:*"):
        redis_client.delete(k)
        # print("已经删掉了", k)

    return {"msg": "成功发布"}

@router.get("",  response_model=List[QuestionOut])
async def list_questions(
        sort: QuestionSort = QuestionSort.hot,
        db: Session = Depends(get_db),
        page: int = Query(1,ge=1,description="页码从1开始"),
        size: int = Query(10,ge=1,le=100, description="每页的内容数量"),
):
    offset = (page-1)*size
    key = f"questions:{sort.value}:{page}:{size}"
    data = redis_client.get(key)
    if data:
        # print("【命中缓存】不用查库了")
        return json.loads(data)

    if sort == QuestionSort.new:
        questions = db.query(Question).order_by(Question.created_at.desc())
        paginate(questions, page, size)
    else:
        hot_expr = func.log2(Question.view_count + 1) + Question.answer_count * 10
        questions = db.query(Question).order_by(hot_expr.desc())
        paginate(questions, page, size)
        # 在原表的基础上进行修改，sort返回值是none
        # questions = db.query(Question).all()
        # all_questions = sorted(questions, key = lambda q:q.hot_score(), reverse=True)
        # questions = all_questions[offset: offset + size]
        # 重新复制给新的表，sorted返回值是一个新的列表
        # questions = questions.sorted(key = lambda q:q.hot_score(), reverse=True)
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
    redis_client.set(key, json.dumps(result, default=str), ex=60)
    # print("【未命中】查了数据库")
    return result

@router.get("/{id}",  response_model=QuestionOut)
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
