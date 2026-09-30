"""隔离回归：覆盖之前遗漏的点赞、AI、RAG 和后台任务路径。"""
import asyncio
from importlib import import_module

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Question, User


def test_all_cache_paths_use_test_redis(_isolate_redis):
    for name in (
        "app.core.redis_client", "app.main", "app.routers.questions",
        "app.routers.answers", "app.routers.like", "app.routers.auth",
        "app.routers.ai", "app.core.tools", "app.core.rag",
    ):
        assert import_module(name).redis_client is _isolate_redis, name
    assert _isolate_redis.connection_pool.connection_kwargs["db"] == 15


def test_background_and_tool_sessions_use_test_database(test_engine):
    for name in ("app.db.base", "app.main", "app.core.tools",
                 "app.core.kb_sync", "app.core.build_kb"):
        with import_module(name).SessionLocal() as session:
            assert session.get_bind() is test_engine, name
    assert import_module("app.main").engine is test_engine


def test_api_lifespan_never_starts_workers_or_creates_tables(monkeypatch):
    main = import_module("app.main")

    def forbidden(*args, **kwargs):
        pytest.fail("接口测试不应启动后台任务或调用建表")

    monkeypatch.setattr(main, "sync_view_count", forbidden)
    monkeypatch.setattr(main, "rebuild_kb_periodic", forbidden)
    monkeypatch.setattr(main.Base.metadata, "create_all", forbidden)
    with TestClient(app) as client:
        assert client.get("/").status_code == 200


def test_view_sync_runs_one_cycle_only_on_isolated_dependencies(
        db_session, _isolate_redis, monkeypatch):
    main = import_module("app.main")
    user = User(username="view_worker", password_hash="unused")
    db_session.add(user)
    db_session.flush()
    question = Question(author_id=user.id, title="隔离测试", content="内容")
    db_session.add(question)
    db_session.commit()
    key = f"question:views:{question.id}"
    _isolate_redis.set(key, 7)
    sleeps = 0

    async def one_cycle(_):
        nonlocal sleeps
        sleeps += 1
        if sleeps > 1:
            raise asyncio.CancelledError

    monkeypatch.setattr(main.asyncio, "sleep", one_cycle)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(main.sync_view_count())
    # Worker 使用独立事务；结束观察会话的旧快照后再验证已提交结果。
    db_session.rollback()
    db_session.refresh(question)
    assert question.view_count == 7
    assert _isolate_redis.get(key) is None


def test_development_vectorstore_is_blocked():
    for name in ("app.core.rag", "app.core.build_kb"):
        with pytest.raises(AssertionError, match="开发 Chroma"):
            import_module(name).vectorstore.get()
