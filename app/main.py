from fastapi import FastAPI
from app.models import User, Question, Answer, Like
from app.db.base import Base, engine
from app.routers import auth, questions, answers, like

app = FastAPI(title="问答社区")

# 挂载各路由模块
app.include_router(auth.router)
app.include_router(questions.router)
app.include_router(answers.router)
app.include_router(answers.answer_router)
app.include_router(like.router)
@app.on_event("startup")
def on_startup():
    # 启动时自动建表，已存在的表自动跳过
    Base.metadata.create_all(bind=engine)


@app.get("/")
async def root():
    return {"message": "QA is ready"}


# if __name__ == '__main__':
#     import uvicorn
#     uvicorn.run(app, host="localhost", port=8000)
