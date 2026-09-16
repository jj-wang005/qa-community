from sqlalchemy.orm import Session

from app.models.kb_outbox import KbOutbox


def enqueue_kb_sync(db: Session, question_id: int, operation: str = "upsert") -> None:
    """在调用方的同一事务中记录索引变更，不能单独提交。"""
    if operation not in {"upsert", "delete"}:
        raise ValueError("Unsupported knowledge-base operation")
    db.add(KbOutbox(question_id=question_id, operation=operation))
