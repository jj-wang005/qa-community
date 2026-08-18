"""
tests/conftest.py —— 所有测试共享的「脚手架」

pytest 会自动加载这个文件，里面定义的都是 fixture（夹具）。
它负责三个隔离，让测试不污染真实环境：
1. 数据库隔离：用独立的 qa_db_test，绝不碰真实库 qa_db
2. 依赖改道：用 dependency_overrides 把 get_db 指向测试库
3. 缓存隔离：Redis 用独立的 db=15，测试缓存不进开发环境的 db=0
"""
import os
import sys

# 把项目根目录加入 sys.path，保证 `from app.xxx import ...` 能找到模块。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import redis
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.base import Base, get_db
from app.main import app
from app.routers import questions as questions_router
from app.routers import answers as answers_router
from app.routers import auth as auth_router
# noqa: F401 是告诉 linter「这几行 import 了但没用，别报警」
# 必须 import，否则 Base.metadata 里没这几张表，create_all 不会建它们
from app.models import User, Question, Answer, Like  # noqa: F401

TEST_DB_NAME = "qa_db_test"


@pytest.fixture(scope="session")
def test_engine():
    """创建一个指向测试库的引擎，全程只跑一次。"""
    base_url, _ = settings.DATABASE_URL.rsplit("/", 1)

    # 第一步：先连「不带库名」的地址，把测试库建出来
    server_engine = create_engine(f"{base_url}/")
    with server_engine.connect() as conn:
        conn.execute(text(f"CREATE DATABASE IF NOT EXISTS {TEST_DB_NAME}"))
        conn.commit()
    server_engine.dispose()

    # 第二步：建一个指向 qa_db_test 的引擎
    engine = create_engine(f"{base_url}/{TEST_DB_NAME}")
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def _clean_tables(test_engine):
    """每个测试开始前，把测试库的表推倒重建，保证用例之间互不干扰。

    autouse=True 表示「不用每个测试声明，自动生效」。
    先 drop 再 create，比手动删数据更干净、更省心。
    """
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    yield


@pytest.fixture(autouse=True)
def _isolate_redis():
    """每个测试用独立的 Redis db=15，并清空它。

    这样测试写入的缓存不会混进你开发环境用的 db=0，
    也保证每个测试看到的缓存状态是全新的。
    """
    fake = redis.Redis(host="localhost", port=6379, db=15, decode_responses=True)
    fake.flushdb()

    # 所有路由模块各自 import 了一份 redis_client 引用，必须逐个替换，测试结束再换回来
    original_clients = {
        questions_router: questions_router.redis_client,
        answers_router: answers_router.redis_client,
        auth_router: auth_router.redis_client,
    }
    for mod in original_clients:
        mod.redis_client = fake
    yield
    for mod, original in original_clients.items():
        mod.redis_client = original
    fake.flushdb()


@pytest.fixture()
def db_session(test_engine):
    """返回一个指向测试库的会话，供测试直接查库验证数据（如 like_count 落库）。"""
    TestSessionLocal = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def client(test_engine):
    """返回一个 TestClient，它的 get_db 依赖被改道到测试库。
    dependency_overrides 是 FastAPI 专门为测试提供的「后门」：
    不用改业务代码，就能把依赖替换掉。
    """
    TestSessionLocal = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    # with 语句会触发 app 的 startup 事件
    with TestClient(app) as c:
        yield c

    app.dependency_overrides.pop(get_db, None)


@pytest.fixture()
def auth(client):
    """注册 + 登录的助手：返回一个函数，调用它就能拿到 token。

    用法：token = auth()                # 默认用户 alice
          token = auth(username="bob")  # 指定用户名
    所有测试文件都能直接用（conftest 的 fixture 自动可见），不用 import。
    """
    def _register_and_login(username="alice", password="secret123"):
        client.post("/api/v1/auth/register", json={"username": username, "password": password})
        resp = client.post("/api/v1/auth/login", json={"username": username, "password": password})
        return resp.json()["access_token"]
    return _register_and_login
