from jose import jwt
from passlib.context import CryptContext
from datetime import datetime, timedelta
import uuid
from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
def get_password_hash(password) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(user_id: int) -> str:
    """签发 JWT token，载荷里放 user_id 和过期时间"""
    expire = datetime.now() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {"sub": str(user_id),"type":"access", "exp": expire}
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(user_id: int, family_id: str) -> tuple[str, str]:
    jti = uuid.uuid4().hex
    expire = datetime.now() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode = {"sub": str(user_id), "type": "refresh", "exp": expire, "jti": jti, "family_id": family_id}
    token = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return token, jti


def decode_token(token: str, expected_type: str) -> tuple[int | None, str | None, str | None]:
    """解析 token，成功返回 (user_id, jti, family_id)，失败返回 (None, None, None)"""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        jti = payload.get("jti")
        family_id = payload.get("family_id")
        if payload.get("type") != expected_type:
            return None, None, None
        return int(payload.get("sub")), jti, family_id
    except Exception:
        return None, None, None


