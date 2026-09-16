from datetime import datetime

from sqlalchemy.orm import sessionmaker

from app.core import kb_sync
from app.models import KbOutbox


def test_create_question_records_kb_outbox_event(client, auth, db_session):
    """问题写入与待同步事件一起提交，Worker 之后才能可靠地更新派生索引。"""
    token = auth()
    response = client.post(
        "/api/v1/questions",
        json={"title": "实时同步测试", "content": "内容"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    event = db_session.query(KbOutbox).one()
    assert event.question_id > 0
    assert event.operation == "upsert"
    assert event.status == "pending"


def test_outbox_worker_merges_events_and_refreshes_derived_indexes(
        test_engine, db_session, monkeypatch
):
    """同一 qid 的多个事件只触发一次向量同步和一次 BM25 刷新。"""
    db_session.add_all([
        KbOutbox(question_id=12, operation="upsert", created_at=datetime(2000, 1, 1)),
        KbOutbox(question_id=12, operation="upsert", created_at=datetime(2000, 1, 1)),
        KbOutbox(question_id=18, operation="delete", created_at=datetime(2000, 1, 1)),
    ])
    db_session.commit()
    test_session = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)
    called = {"question_ids": None, "bm25": 0, "cache": 0}

    monkeypatch.setattr(kb_sync, "SessionLocal", test_session)
    monkeypatch.setattr(kb_sync.settings, "KB_SYNC_DEBOUNCE_SECONDS", 0)
    monkeypatch.setattr(
        kb_sync.build_kb,
        "sync_question_ids",
        lambda question_ids: called.update(question_ids=question_ids) or {
            "新增": 1, "更新": 1, "跳过": 0, "删除": 1,
        },
    )
    monkeypatch.setattr(kb_sync, "build_bm25_index", lambda: called.update(bm25=called["bm25"] + 1))
    monkeypatch.setattr(kb_sync, "invalidate_rag_cache", lambda: called.update(cache=called["cache"] + 1))

    stats = kb_sync.process_kb_outbox()

    assert stats["事件"] == 3
    assert called["question_ids"] == {12, 18}
    assert called["bm25"] == 1
    assert called["cache"] == 1
    db_session.expire_all()
    assert {event.status for event in db_session.query(KbOutbox).all()} == {"done"}
