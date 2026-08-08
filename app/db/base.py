from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from app.core.config import settings

#建立所有模型的基类
class Base(DeclarativeBase):
    pass

#建立数据库会话引擎
engine = create_engine(
    settings.DATABASE_URL
)

#建立会话工厂
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

#获取数据库会话
def get_db():
    db= SessionLocal()
    try:
        yield db
    finally:
        db.close()
