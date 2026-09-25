import json
from datetime import datetime
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests
from langchain_core.tools import tool
from sqlalchemy import or_, select

from app.core.redis_client import redis_client
from app.core.kb_events import enqueue_kb_sync
from app.db.base import SessionLocal
from app.models import Answer, Question
from app.models.like import Like


@tool
def search_master(query: str) -> str:
    """检索社区离线知识库，返回与问题最相关的问答资料及来源标题（结构化文本）。
    当用户问题涉及社区已有内容、技术知识点、历史讨论时统一调用本工具检索。"""
    from app.core.rag import format_context, search

    hits = search(query)
    if hits:
        return format_context(hits)
    return "离线知识库中检索不到相关资料"


@tool
def search_live_questions(query: str = "", limit: int = 5) -> str:
    """查询社区当前问题，用于最新、刚发布、当前动态或按标题/正文精确查找。
    此工具直接读取业务数据库；结果反映查询时状态，不用于历史语义检索。"""
    limit = min(max(limit, 1), 10)
    with SessionLocal() as db:
        stmt = select(Question)
        normalized = query.strip()
        if normalized:
            pattern = f"%{normalized}%"
            stmt = stmt.where(or_(Question.title.like(pattern), Question.content.like(pattern)))
        questions = db.scalars(
            stmt.order_by(Question.created_at.desc(), Question.id.desc()).limit(limit)
        ).all()
    items = [
        {
            "qid": question.id,
            "title": question.title,
            "content": question.content[:300],
            "answer_count": question.answer_count,
            "created_at": question.created_at.isoformat() if question.created_at else None,
            "updated_at": question.updated_at.isoformat() if question.updated_at else  None,
        }
        for question in questions
    ]
    return json.dumps({"source": "mysql_live", "items": items}, ensure_ascii=False)


@tool
def get_weather(city: str) -> str:
    """获取指定城市的实时天气。当用户询问某地天气、温度时使用。"""
    url = f"https://wttr.in/{quote(city)}?format=3"
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    return resp.text


_WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


@tool
def get_time() -> str:
    """获取当前时间（北京时间）。当用户询问现在几点、今天日期时使用。"""
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    return f"{now:%Y-%m-%d %H:%M:%S} {_WEEKDAYS[now.weekday()]}"


@tool
def get_location() -> str:
    """获取当前网络所在地区（国家、省份、城市）。当用户询问"我在哪"时使用。"""
    resp = requests.get("http://ip-api.com/json/?lang=zh-CN", timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if data.get("status") != "success":
        return "无法定位当前地区"
    return f"{data.get('country')} {data.get('regionName')} {data.get('city')}"


@tool
def get_answers(question_id: int) -> str:
    """获取指定问题下的回答列表，返回回答 ID、内容摘要与点赞数。当用户需要查看某问题的回答、或要求对回答进行操作时使用。"""
    with SessionLocal() as db:
        stmt = (
            select(Answer)
            .where(Answer.question_id == question_id)
            .order_by(Answer.like_count.desc())
            .limit(10)
        )
        answers = db.scalars(stmt).all()

    items = [
        {
            "id": a.id,
            "content": a.content[:100],
            "like_count": a.like_count,
        }
        for a in answers
    ]
    return json.dumps(items, ensure_ascii=False)


def make_write_tools(user_id: int) -> list:
    """创建绑定当前登录用户身份的写操作工具。user_id 通过闭包注入，对 LLM 不可见，避免越权操作。"""

    @tool
    def like_answer(answer_id: int) -> str:
        """给指定回答点赞（以当前用户身份）。当用户要求给某条回答点赞时使用。"""
        with SessionLocal() as db:
            answer = db.get(Answer, answer_id)
            if answer is None:
                return "点赞失败：回答不存在"
            liked = db.query(Like).filter(
                Like.user_id == user_id, Like.answer_id == answer_id
            ).first()
            if liked:
                return "点赞失败：该回答已经点过赞了"
            db.add(Like(user_id=user_id, answer_id=answer_id))
            answer.like_count += 1
            # 点赞可能改变“最高赞回答”的选择；hash 未变化时 Worker 会自动跳过。
            enqueue_kb_sync(db, answer.question_id)
            db.commit()
            # 失效该问题下回答列表的缓存，保证数据一致
            for k in redis_client.scan_iter(f"answers:*:{answer.question_id}:*"):
                redis_client.delete(k)
            return f"点赞成功，已立即写入数据库，该回答当前点赞数 {answer.like_count}"

    return [like_answer]
