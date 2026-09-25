import asyncio
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.core.exceptions import (
    http_exception_handler,
    validation_exception_handler,
    unhandled_exception_handler,
)
from app.core.redis_client import redis_client
from app.core.config import settings
from app.core.kb_sync import rebuild_kb_periodic
from app.models import User, Question, Answer, Like, KbOutbox  # noqa: F401 确保模型注册进 Base.metadata
from app.db.base import Base, engine, SessionLocal
from app.routers import auth, questions, answers, like, ai


async def sync_view_count():
    while True:
        await asyncio.sleep(60)
        keys = redis_client.scan_iter(f"question:views:*")
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
    kb_task = asyncio.create_task(rebuild_kb_periodic())
    yield
    kb_task.cancel()
    task.cancel()


app = FastAPI(title="问答社区", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

# API v1 路由：所有接口挂在 /api/v1 前缀下，后续新增 v2 时新旧并存
api_v1 = APIRouter(prefix="/api/v1")
api_v1.include_router(auth.router)
api_v1.include_router(questions.router)
api_v1.include_router(answers.router)
api_v1.include_router(answers.answer_router)
api_v1.include_router(like.router)
api_v1.include_router(ai.router)

app.include_router(api_v1)

@app.get("/")
async def root():
    return {"message": "QA is ready"}
