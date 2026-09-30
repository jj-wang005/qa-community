"""
tests/conftest.py —— 所有测试共享的「脚手架」

pytest 会自动加载这个文件，里面定义的都是 fixture（夹具）。
测试资源边界（qa_db_test 和 Redis db=15 必须专用于测试，不可并行运行本套件）：
1. 数据库隔离：用独立的 qa_db_test，绝不碰真实库 qa_db
2. 依赖改道：用 dependency_overrides 把 get_db 指向测试库
3. 缓存隔离：Redis 用独立的 db=15，测试缓存不进开发环境的 db=0
4. 生命周期隔离：接口测试不启动后台任务，任务测试显式调用单轮逻辑
5. 向量库保护：调用开发 Chroma 会直接失败，任务测试必须注入替身
"""
import os
import sys
from contextlib import asynccontextmanager
from importlib import import_module

# 把项目根目录加入 sys.path，保证 `from app.xxx import ...` 能找到模块。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import redis
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.engine import make_url

from app.core.config import settings
from app.db.base import Base, get_db
from app.main import app
# noqa: F401 是告诉 linter「这几行 import 了但没用，别报警」
# 必须 import，否则 Base.metadata 里没这几张表，create_all 不会建它们
from app.models import User, Question, Answer, Like, KbOutbox  # noqa: F401

TEST_DB_NAME = "qa_db_test"


def _replace_app_references(monkeypatch, original, replacement):
    """替换已导入的应用别名，也覆盖后续 import 的源模块。"""
    for name, module in list(sys.modules.items()):
        if module is not None and (name == "app" or name.startswith("app.")):
            for attr, value in list(vars(module).items()):
                if value is original:
                    monkeypatch.setattr(module, attr, replacement)


@pytest.fixture(scope="session")
def test_engine():
    """创建一个指向测试库的引擎，全程只跑一次。"""
    source_url = make_url(settings.DATABASE_URL)
    if source_url.database == TEST_DB_NAME:
        raise RuntimeError("开发数据库不能与测试数据库同名")

    # 第一步：先连「不带库名」的地址，把测试库建出来
    server_engine = create_engine(source_url.set(database=""))
    try:
        with server_engine.connect() as conn:
            conn.execute(text(f"CREATE DATABASE IF NOT EXISTS {TEST_DB_NAME}"))
            conn.commit()
    finally:
        server_engine.dispose()

    # 第二步：建一个指向 qa_db_test 的引擎
    engine = create_engine(source_url.set(database=TEST_DB_NAME))
    try:
        yield engine
    finally:
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
def _isolate_redis(monkeypatch):
    """每个测试用独立的 Redis db=15，并清空它。

    这样测试写入的缓存不会混进你开发环境用的 db=0，
    也保证每个测试看到的缓存状态是全新的。
    """
    source = import_module("app.core.redis_client").redis_client
    if source.connection_pool.connection_kwargs.get("db", 0) == 15:
        raise RuntimeError("开发 Redis 不能使用测试专用 db=15")
    fake = redis.Redis(host="localhost", port=6379, db=15, decode_responses=True,
                       socket_connect_timeout=5, socket_timeout=5)
    fake.flushdb()

    # 所有路由模块各自 import 了一份 redis_client 引用，必须逐个替换，测试结束再换回来
    _replace_app_references(monkeypatch, source, fake)
    try:
        yield fake
    finally:
        try:
            fake.flushdb()
        finally:
            fake.close()


@pytest.fixture(autouse=True)
def _isolate_database_references(test_engine, monkeypatch):
    """工具、后台任务和源模块的直接会话/引擎引用统一指向测试库。"""
    TestSessionLocal = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)
    base = import_module("app.db.base")
    _replace_app_references(monkeypatch, base.SessionLocal, TestSessionLocal)
    _replace_app_references(monkeypatch, base.engine, test_engine)


@pytest.fixture(autouse=True)
def _isolate_lifespan(monkeypatch):
    """接口测试不建开发表、不启动周期任务；任务由专门测试直接调用。"""
    @asynccontextmanager
    async def test_lifespan(application):
        yield

    monkeypatch.setattr(app.router, "lifespan_context", test_lifespan)


@pytest.fixture(autouse=True)
def _block_development_vectorstore(monkeypatch):
    """后台任务测试必须显式注入向量替身，禁止读写开发 Chroma。"""
    class BlockedVectorStore:
        def __getattr__(self, name):
            raise AssertionError("测试必须注入隔离的 vectorstore，禁止访问开发 Chroma")

    rag = import_module("app.core.rag")
    _replace_app_references(monkeypatch, rag.vectorstore, BlockedVectorStore())


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

    # 使用隔离 lifespan，仍然验证 TestClient 的正常进入和退出。
    try:
        with TestClient(app) as c:
            yield c
    finally:
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
