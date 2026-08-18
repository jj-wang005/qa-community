from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.db.base import get_db
from app.models.user import User

# 从请求头 Authorization: Bearer xxx 里取 token 的工具
security = HTTPBearer()


def get_current_user(
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> User:
    """从请求头解析 token，返回当前登录用户；无效则 401"""
    token = credentials.credentials
    user_id, _, _ = decode_token(token, "access")
    if user_id is None:
        raise HTTPException(status_code=401, detail="token 无效或已过期")

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="用户不存在")
    return user
