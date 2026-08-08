from jose import jwt
from passlib.context import CryptContext
from datetime import datetime, timedelta

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
def get_password_hash(password) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(user_id: int) -> str:
    """签发 JWT token，载荷里放 user_id 和过期时间"""
    expire = datetime.now() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {"sub": str(user_id), "exp": expire}
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> int | None:
    """解析 token，成功返回 user_id，失败返回 None"""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return int(payload.get("sub"))
    except Exception:
        return None


