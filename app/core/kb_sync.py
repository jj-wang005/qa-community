import asyncio
import logging

from app.core import build_kb
from app.core.config import settings

logger = logging.getLogger(__name__)


async def rebuild_kb_periodic() -> None:
    """定时增量同步离线知识库：每隔 KB_REBUILD_INTERVAL_HOURS 小时同步一次，只更新变化的文档。"""
    interval = settings.KB_REBUILD_INTERVAL_HOURS * 3600
    while True:
        await asyncio.sleep(interval)
        try:
            # 建库是同步 CPU 密集操作，丢到线程池避免阻塞事件循环
            stats = await asyncio.to_thread(build_kb.sync_kb_incremental)
            logger.info("离线知识库定时同步完成：%s", stats)
        except Exception:
            logger.exception("离线知识库定时同步失败")