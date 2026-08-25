from langchain_core.documents import Document

from app.core.rag import vectorstore
from app.db.base import SessionLocal
from app.models.answer import Answer
from app.models.question import Question

def get_documents(db):
    """读取真实问答，返回 [{text, source}, ...]"""
    docs = []
    questions = (
        db.query(Question)
        .filter(~Question.title.like("测试%"), ~Question.title.like("调试题%"))
        .all()
    )
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

    documents = [
        Document(page_content=d["text"], metadata=d["source"]) for d in docs
    ]
    vectorstore.add_documents(documents)
    print(f"入库 {len(docs)} 块完成")
    db.close()


if __name__ == "__main__":
    main()
