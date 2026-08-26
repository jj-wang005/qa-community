import asyncio
import logging

from app.core import build_kb
from app.core.config import settings

logger = logging.getLogger(__name__)


async def rebuild_kb_periodic() -> None:
    """定时重建离线知识库：每隔 KB_REBUILD_INTERVAL_HOURS 小时全量重建一次。"""
    interval = settings.KB_REBUILD_INTERVAL_HOURS * 3600
    while True:
        await asyncio.sleep(interval)
        try:
            # 建库是同步 CPU 密集操作，丢到线程池避免阻塞事件循环
            await asyncio.to_thread(build_kb.main)
            logger.info("离线知识库定时重建完成")
        except Exception:
            logger.exception("离线知识库定时重建失败")