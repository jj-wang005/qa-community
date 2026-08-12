from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.models import User, Question, Answer, Like  # noqa: F401 确保模型注册进 Base.metadata
from app.db.base import Base, engine
from app.routers import auth, questions, answers, like


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时自动建表，已存在的表自动跳过
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="问答社区", lifespan=lifespan)

# 挂载各路由模块
app.include_router(auth.router)
app.include_router(questions.router)
app.include_router(answers.router)
app.include_router(answers.answer_router)
app.include_router(like.router)


@app.get("/")
async def root():
    return {"message": "QA is ready"}
