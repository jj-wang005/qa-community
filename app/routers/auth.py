import json

from fastapi import APIRouter, Depends, HTTPException

from app.core.config import settings
from app.schemas.user import RegisterUser, RefreshToken
from sqlalchemy.orm import Session
from app.db.base import get_db
from app.core.security import get_password_hash, verify_password, create_access_token, create_refresh_token, \
    decode_token
from app.models.user import User
from app.core.redis import redis_client


router = APIRouter(prefix="/auth", tags=["认证"])

@router.post("/register")
def register(payload: RegisterUser, db: Session = Depends(get_db)):
    exist = db.query(User).filter(User.username == payload.username).first()
    if exist:
            raise HTTPException(status_code=400, detail="用户已存在")
    user = User(username = payload.username, password_hash = get_password_hash(payload.password))
    db.add(user)
    db.commit()
    return {"message": "注册成功"}

@router.post("/login")
def login(payload: RegisterUser, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == payload.username).first()
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    access_token = create_access_token(user.id)
    refresh_token, jti = create_refresh_token(user.id)
    cache_key = f"refresh:{jti}"
    redis_client.set(cache_key, user.id, ex=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60)
    return {"msg":"登录成功", "access_token":access_token, "refresh_token": refresh_token, "token_type": "bearer"}

@router.post("/refresh")
def refresh_token(
        payload: RefreshToken,
        db:Session = Depends(get_db)
):
    user_id,jti = decode_token(payload.refresh_token, "refresh")
    if user_id is None:
        raise HTTPException(status_code=401, detail="token失效")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    if redis_client.get(f"refresh:{jti}") is None:
        raise HTTPException(status_code=401, detail="过期请重新登录")
    redis_client.delete(f"refresh:{jti}")
    new_access = create_access_token(user_id)
    new_refresh, new_jti = create_refresh_token(user_id)
    redis_client.set(f"refresh:{new_jti}", user_id, ex=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60)
    return {"access_token": new_access, "refresh_token": new_refresh, "token_type": "bearer"}
