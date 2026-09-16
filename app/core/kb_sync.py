import asyncio
import logging
import threading
from datetime import datetime, timedelta

from app.core import build_kb
from app.core.config import settings
from app.core.rag import build_bm25_index, invalidate_rag_cache
from app.db.base import SessionLocal
from app.models.kb_outbox import KbOutbox

logger = logging.getLogger(__name__)
_worker_lock = threading.Lock()


def _has_changes(stats: dict) -> bool:
    return any(stats.get(key, 0) for key in ("新增", "更新", "删除"))


def process_kb_outbox() -> dict:
    """处理一批已过合并窗口的事件；仅支持单应用 Worker 运行。"""
    if not _worker_lock.acquire(blocking=False):
        return {"状态": "busy"}
    try:
        cutoff = datetime.now() - timedelta(seconds=settings.KB_SYNC_DEBOUNCE_SECONDS)
        db = SessionLocal()
        try:
            events = (
                db.query(KbOutbox)
                .filter(KbOutbox.status == "pending", KbOutbox.created_at <= cutoff)
                .order_by(KbOutbox.id.asc())
                .limit(settings.KB_SYNC_BATCH_SIZE)
                .all()
            )
            if not events:
                return {"事件": 0, "新增": 0, "更新": 0, "跳过": 0, "删除": 0}
            # 多个旧事件可合并；同步时读取数据库最终状态，天然避免旧事件覆盖新内容。
            question_ids = {event.question_id for event in events}
            try:
                stats = build_kb.sync_question_ids(question_ids)
                if _has_changes(stats):
                    build_bm25_index()
                    invalidate_rag_cache()
                now = datetime.now()
                for event in events:
                    event.status = "done"
                    event.completed_at = now
                    event.last_error = None
                db.commit()
                return {"事件": len(events), **stats}
            except Exception as exc:
                for event in events:
                    event.attempts += 1
                    event.last_error = type(exc).__name__
                db.commit()
                raise
        finally:
            db.close()
    finally:
        _worker_lock.release()


async def rebuild_kb_periodic() -> None:
    """持续消费 Outbox，并按原有间隔全量校验一次，防止历史漏同步。"""
    reconcile_interval = settings.KB_FULL_RECONCILE_INTERVAL_HOURS * 3600
    last_reconcile = asyncio.get_running_loop().time()
    while True:
        await asyncio.sleep(settings.KB_SYNC_POLL_SECONDS)
        try:
            stats = await asyncio.to_thread(process_kb_outbox)
            if stats.get("事件"):
                logger.info("知识库 Outbox 同步完成：%s", stats)
        except Exception:
            logger.exception("知识库 Outbox 同步失败")

        now = asyncio.get_running_loop().time()
        if now - last_reconcile >= reconcile_interval:
            try:
                stats = await asyncio.to_thread(build_kb.sync_kb_incremental)
                if _has_changes(stats):
                    await asyncio.to_thread(build_bm25_index)
                    invalidate_rag_cache()
                logger.info("离线知识库全量校验完成：%s", stats)
            except Exception:
                logger.exception("离线知识库全量校验失败")
            last_reconcile = now
