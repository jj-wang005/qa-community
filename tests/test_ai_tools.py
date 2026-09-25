"""
tests/test_ai_tools.py —— AI 工具函数的自动化测试

只测「工具本身」的确定性行为（不经过 LLM，离线可重复）：
- get_answers：按点赞数排序返回回答列表
- like_answer：以闭包绑定的身份写库、清缓存、防重复

AI agent 真实链路（POST /ai/chat 会调 MiMo 外网 API）依赖外部服务 + API key，
不适合进常规 pytest，放 scripts/e2e_tools_test.py 手动跑。
"""

import json

from app.core.tools import get_answers, make_write_tools, search_live_questions
from app.core import tools as tools_module
from app.models import User, Question, Answer, Like, KbOutbox


def _seed_user(db_session, username="tester"):
    """建一个真实用户（三个表都有外键，必须存在才能写 Like）。"""
    u = User(username=username, password_hash="hash")
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u


def _seed_question_with_answer(db_session, user, title, like_count=0):
    q = Question(title=title, content="问题内容", author_id=user.id)
    db_session.add(q)
    db_session.commit()
    db_session.refresh(q)
    a = Answer(content="回答内容", question_id=q.id, author_id=user.id, like_count=like_count)
    db_session.add(a)
    db_session.commit()
    db_session.refresh(a)
    return q, a


def test_get_answers_sorted_by_like_count(db_session):
    """回答列表按点赞数从高到低排序。"""
    user = _seed_user(db_session)
    q = Question(title="标题", content="内容", author_id=user.id)
    db_session.add(q)
    db_session.commit()
    db_session.refresh(q)
    db_session.add_all([
        Answer(content="低赞", question_id=q.id, author_id=user.id, like_count=1),
        Answer(content="高赞", question_id=q.id, author_id=user.id, like_count=9),
    ])
    db_session.commit()

    out = json.loads(get_answers.invoke({"question_id": q.id}))
    likes = [it["like_count"] for it in out]
    assert likes == sorted(likes, reverse=True)
    assert out[0]["id"] != out[1]["id"]


def test_like_answer_writes_db_and_clears_cache(db_session):
    """点赞写库（Like 记录 + like_count+1），并清掉该问题下回答列表缓存。"""
    user = _seed_user(db_session)
    q, a = _seed_question_with_answer(db_session, user, title="题", like_count=3)
    like_answer = make_write_tools(user_id=user.id)[0]

    # 预造一条缓存，模拟「回答列表已被缓存」的场景
    cache_key = f"answers:hot:{q.id}:1:10"
    tools_module.redis_client.set(cache_key, "cached")

    out = like_answer.invoke({"answer_id": a.id})
    assert "点赞成功" in out

    # 工具在另一个会话里 commit 了，这里先提交结束旧事务，才能拿到新快照的数据
    db_session.commit()
    assert a.like_count == 4
    assert db_session.query(Like).filter_by(user_id=user.id, answer_id=a.id).first() is not None
    assert db_session.query(KbOutbox).filter_by(question_id=q.id, operation="upsert").count() == 1
    assert not tools_module.redis_client.exists(cache_key)


def test_like_answer_rejects_duplicate(db_session):
    """同一用户对同一回答重复点赞被拒，like_count 只加一次。"""
    user = _seed_user(db_session)
    _, a = _seed_question_with_answer(db_session, user, title="题", like_count=3)
    like_answer = make_write_tools(user_id=user.id)[0]

    like_answer.invoke({"answer_id": a.id})
    out = like_answer.invoke({"answer_id": a.id})
    assert "已经点过赞" in out

    db_session.commit()
    assert a.like_count == 4


def test_like_answer_missing_answer(db_session):
    """回答不存在时返回失败提示，不抛异常。"""
    user = _seed_user(db_session)
    like_answer = make_write_tools(user_id=user.id)[0]
    out = like_answer.invoke({"answer_id": 99999})
    assert "回答不存在" in out


def test_search_live_questions_reads_current_mysql_data(db_session):
    """实时 Tool 按创建时间读取 MySQL，不经过 Chroma 或 BM25。"""
    user = _seed_user(db_session)
    older = Question(title="JWT 旧问题", content="旧内容", author_id=user.id)
    newer = Question(title="JWT 新问题", content="新内容", author_id=user.id)
    db_session.add_all([older, newer])
    db_session.commit()

    result = json.loads(search_live_questions.invoke({"query": "JWT", "limit": 1}))

    assert result["source"] == "mysql_live"
    assert len(result["items"]) == 1
    assert result["items"][0]["qid"] == newer.id
    assert result["items"][0]["title"] == "JWT 新问题"
