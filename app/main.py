import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError

from app.core.exceptions import (
    http_exception_handler,
    validation_exception_handler,
    unhandled_exception_handler,
)
from app.core.redis import redis_client
from app.models import User, Question, Answer, Like  # noqa: F401 确保模型注册进 Base.metadata
from app.db.base import Base, engine, SessionLocal
from app.routers import auth, questions, answers, like

async def sync_view_count():
    while True:
        await asyncio.sleep(60)
        keys = redis_client.keys(f"question:views:*")
        db = SessionLocal()
        try:
            for k in keys:
                qid = int(k.split(":")[-1])
                questions = db.get(Question, qid)
                if questions:
                    questions.view_count = int(redis_client.get(k))
                    redis_client.delete(k)
                db.commit()
        finally:
            db.close()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时自动建表，已存在的表自动跳过
    Base.metadata.create_all(bind=engine)
    task = asyncio.create_task(sync_view_count())
    yield


app = FastAPI(title="问答社区", lifespan=lifespan)

app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

# 挂载各路由模块
app.include_router(auth.router)
app.include_router(questions.router)
app.include_router(answers.router)
app.include_router(answers.answer_router)
app.include_router(like.router)

@app.get("/")
async def root():
    return {"message": "QA is ready"}
