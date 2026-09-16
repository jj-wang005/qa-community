import hashlib
from langchain_core.documents import Document

from app.core.rag import vectorstore
from app.db.base import SessionLocal
from app.models.answer import Answer
from app.models.question import Question


def get_documents(db):
    """读取真实问答，返回 [{text, source}, ...]，source 含标题、问题 id 与内容指纹。"""
    return [_document_for_question(db, question) for question in db.query(Question).all()]


def _document_for_question(db, question):
    """把一个问题及最值得引用的回答组装成可向量化文档。"""
    answer = (
        db.query(Answer)
        .filter(Answer.question_id == question.id)
        .order_by(Answer.is_accepted.desc(), Answer.like_count.desc(), Answer.id.asc())
        .first()
    )
    text = f"问题：{question.title}\n{question.content}"
    if answer:
        text += f"\n回答：{answer.content[:500]}"
    return {
        "text": text,
        "source": {
            "title": question.title,
            "qid": question.id,
            "hash": hashlib.md5(text.encode("utf-8")).hexdigest(),
        },
    }


# Chroma 单次批量写入有上限（默认 5461 条），数据量大时必须分批提交
_ADD_BATCH = 1000


def _add_documents(docs) -> None:
    """按 question_id 作为向量文档 id 写入；重复 id 覆盖旧向量（Chroma add 为 upsert 语义）。"""
    for i in range(0, len(docs), _ADD_BATCH):
        batch = docs[i : i + _ADD_BATCH]
        documents = [
            Document(page_content=d["text"], metadata=d["source"]) for d in batch
        ]
        vectorstore.add_documents(
            documents, ids=[str(d["source"]["qid"]) for d in batch]
        )


def rebuild_all() -> int:
    """全量重建：清空向量库后全部重新入库。用于首次构建或需要彻底重建时。"""
    db = SessionLocal()
    docs = get_documents(db)
    db.close()
    if not docs:
        return 0
    vectorstore.reset_collection()
    _add_documents(docs)
    return len(docs)


def sync_kb_incremental() -> dict:
    """ 增量同步离线知识库：只对内容变化的文档重新向量化，未变化的跳过    """
    db = SessionLocal()
    docs = get_documents(db)
    db.close()

    existing = vectorstore.get(include=["metadatas"])
    existing_ids = existing.get("ids", [])
    existing_metas = existing.get("metadatas", [])

    # 旧结构迁移：现有文档未带 qid 指纹（历史 UUID id），一次性全量重建换到新结构
    if existing_ids and not all(meta and "qid" in meta for meta in existing_metas):
        vectorstore.reset_collection()
        _add_documents(docs)
        return {"新增": len(docs), "更新": 0, "跳过": 0, "删除": 0, "模式": "迁移重建"}

    # 建立 qid -> (chroma_id, hash) 映射
    existing_map = {}
    for cid, meta in zip(existing_ids, existing_metas):
        existing_map[int(meta["qid"])] = (cid, meta.get("hash", ""))

    new_qids = {d["source"]["qid"] for d in docs}

    to_add, to_update, to_delete, skipped = [], [], [], 0
    for d in docs:
        qid = d["source"]["qid"]
        if qid not in existing_map:
            to_add.append(d)
        elif existing_map[qid][1] != d["source"]["hash"]:
            to_update.append(d)
        else:
            skipped += 1

    # 向量库中有、数据库已删除的问题 → 删除对应向量
    for qid, (cid, _) in existing_map.items():
        if qid not in new_qids:
            to_delete.append(cid)

    if to_add:
        _add_documents(to_add)
    if to_update:
        _add_documents(to_update)  # 同一 id 覆盖旧向量，无需先删
    if to_delete:
        vectorstore.delete(ids=to_delete)

    return {
        "新增": len(to_add),
        "更新": len(to_update),
        "跳过": skipped,
        "删除": len(to_delete),
    }


def sync_question_ids(question_ids: set[int]) -> dict:
    """按 question_id 同步事件批次；数据库当前状态始终覆盖事件中的旧操作。"""
    ids = sorted({int(question_id) for question_id in question_ids if int(question_id) > 0})
    if not ids:
        return {"新增": 0, "更新": 0, "跳过": 0, "删除": 0}

    existing = vectorstore.get(ids=[str(question_id) for question_id in ids], include=["metadatas"])
    existing_map = {
        int(meta["qid"]): meta
        for meta in existing.get("metadatas", [])
        if meta and meta.get("qid") is not None
    }
    to_write, to_delete, skipped = [], [], 0
    db = SessionLocal()
    try:
        for question_id in ids:
            question = db.get(Question, question_id)
            if question is None:
                if question_id in existing_map:
                    to_delete.append(str(question_id))
                continue
            document = _document_for_question(db, question)
            if existing_map.get(question_id, {}).get("hash") == document["source"]["hash"]:
                skipped += 1
            else:
                to_write.append(document)
    finally:
        db.close()

    if to_write:
        _add_documents(to_write)
    if to_delete:
        vectorstore.delete(ids=to_delete)
    added = sum(document["source"]["qid"] not in existing_map for document in to_write)
    return {
        "新增": added,
        "更新": len(to_write) - added,
        "跳过": skipped,
        "删除": len(to_delete),
    }


def main():
    """兼容旧入口：直接全量重建。"""
    n = rebuild_all()
    print(f"全量重建完成，入库 {n} 块")


if __name__ == "__main__":
    main()
