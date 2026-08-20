"""构建 RAG 知识库：读 MySQL → 合并问答 → 向量化 → 入库（一次性脚本）。
运行方式：python -m app.core.build_kb
"""
from app.core.rag import embed, collection
from app.db.base import SessionLocal
from app.models.answer import Answer
from app.models.question import Question


def get_documents(db):
    """读取真实问答，返回 [{text, source}, ...]"""
    docs = []
    # 在 SQL 层过滤掉「测试」开头的 1 万条垃圾数据，只保留真实问答
    questions = db.query(Question).filter(~Question.title.like("测试%")).all()
    for q in questions:
        # 取该题最值得引用的回答：优先采纳的，其次点赞最多的
        answer = (
            db.query(Answer)
            .filter(Answer.question_id == q.id)
            .order_by(Answer.is_accepted.desc(), Answer.like_count.desc())
            .first()
        )
        text = f"问题：{q.title}\n{q.content}"
        if answer:
            text += f"\n回答：{answer.content[:500]}"
        docs.append({"text": text, "source": {"title": q.title}})
    return docs


def main():
    db = SessionLocal()
    docs = get_documents(db)
    print(f"读取 {len(docs)} 条文档")
    if not docs:
        db.close()
        return

    texts = [d["text"] for d in docs]
    vectors = embed(texts)  # bge 把每块编码成向量

    collection.add(
        ids=[f"doc_{i}" for i in range(len(docs))],
        embeddings=vectors,
        documents=texts,
        metadatas=[d["source"] for d in docs],
    )
    print(f"入库 {len(docs)} 块完成")
    db.close()


if __name__ == "__main__":
    main()
