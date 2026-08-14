from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.redis import redis_client
from app.db.base import get_db
from app.models import User, Answer
from app.models.like import Like

router = APIRouter(prefix="/like", tags=["点赞"])

@router.post("/{answer_id}")
async def like(
        answer_id: int = Path(...,ge=0),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    answer = db.get(Answer, answer_id)
    if not answer:
        raise HTTPException(status_code=404, detail="糟糕，评论不见了")
    like = db.query(Like).filter(Like.user_id == current_user.id, Like.answer_id == answer_id).first()
    if like:
        raise HTTPException(status_code=400, detail="你已经点赞过了")

    new_like = Like(user_id = current_user.id, answer_id = answer_id)
    answer.like_count += 1
    db.add(new_like)
    db.commit()

    for k in redis_client.keys(f"answers:{answer.question_id}:*"):
        redis_client.delete(k)

    return{"msg": "点赞成功","点赞数量": answer.like_count}


