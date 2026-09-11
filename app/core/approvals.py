"""单进程、短期的点赞审批；记录只在成功取走后恢复一次。"""
from dataclasses import dataclass
from threading import Lock
from time import monotonic
from typing import Any
from uuid import uuid4

from fastapi import HTTPException

APPROVAL_TTL = 600
MAX_PENDING = 128


@dataclass
class PendingApproval:
    user_id: int
    session_id: str
    agent: Any
    config: dict
    guard: Any
    history: list[dict]
    action_count: int
    expires_at: float = 0


class ApprovalStore:
    def __init__(self):
        self._pending = {}
        self._lock = Lock()

    def _purge(self):
        now = monotonic()
        for key in list(self._pending):
            if self._pending[key].expires_at <= now:
                del self._pending[key]

    def save(self, pending: PendingApproval) -> str:
        with self._lock:
            self._purge()
            if len(self._pending) >= MAX_PENDING:
                raise HTTPException(503, '待审批请求过多，请稍后重试')
            approval_id = str(uuid4())
            pending.expires_at = monotonic() + APPROVAL_TTL
            self._pending[approval_id] = pending
            return approval_id

    def take(self, approval_id: str, user_id: int, session_id: str, count: int):
        with self._lock:
            self._purge()
            pending = self._pending.get(approval_id)
            if pending is None:
                raise HTTPException(410, '审批已失效或已处理，请重新发起请求')
            if pending.user_id != user_id or pending.session_id != session_id:
                raise HTTPException(404, '审批不存在')
            if pending.action_count != count:
                raise HTTPException(422, '必须按展示顺序为每个操作提供一个决定')
            return self._pending.pop(approval_id)


approval_store = ApprovalStore()
