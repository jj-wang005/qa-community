from fastapi import APIRouter, Depends, HTTPException
from app.schemas.user import RegisterUser
from sqlalchemy.orm import Session
from app.db.base import get_db
from app.core.security import get_password_hash, verify_password, create_access_token
from app.models.user import User


router = APIRouter(prefix="/auth", tags=["认证"])

@router.post("/register")
async def register(payload: RegisterUser, db: Session = Depends(get_db)):
    exist = db.query(User).filter(User.username == payload.username).first()
    if exist:
            raise HTTPException(status_code=400, detail="用户已存在")
    user = User(username = payload.username, password_hash = get_password_hash(payload.password))
    db.add(user)
    db.commit()
    return {"message": "注册成功"}

@router.post("/login")
async def login(payload: RegisterUser, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == payload.username).first()
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    token = create_access_token(user.id)
    return {"msg":"登录成功", "token":token}