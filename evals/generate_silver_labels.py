from __future__ import annotations

import argparse
import json
import warnings
from pathlib import Path

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from app.core import rag
from app.core.config import settings
from evals.dataset import DEFAULT_CASES, load_cases


class RelevanceLabels(BaseModel):
    relevant_qids: list[int] = Field(description="The smallest sufficient set of directly answering qids")
    reference_answer: str = Field(description="A concise answer supported only by the selected documents")
    confidence: float = Field(ge=0, le=1)
    reason: str


def candidate_documents(query: str, limit: int = 12) -> list[dict]:
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Relevance scores must be between 0 and 1")
        vector_docs = rag.vectorstore.similarity_search_with_relevance_scores(query, k=limit)
    vector = [
        {"qid": int(doc.metadata["qid"]), "title": doc.metadata.get("title", ""), "content": doc.page_content}
        for doc, _ in vector_docs if doc.metadata.get("qid") is not None
    ]
    lexical = [
        {"qid": int(hit["source"]["qid"]), "title": hit["source"].get("title", ""), "content": hit["content"]}
        for hit in rag.bm25_search(query, top_k=limit)
        if hit.get("source", {}).get("qid") is not None
    ]
    return list({doc["qid"]: doc for doc in vector + lexical}.values())


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate multi-qid silver relevance labels.")
    parser.add_argument("--input", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output", type=Path, default=Path("evals/data/cases_silver.jsonl"))
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    cases = load_cases(args.input)
    if args.limit:
        cases = cases[: args.limit]
    judge = ChatOpenAI(
        model="deepseek-chat",
        api_key=settings.DEEPSEEK_API_KEY,
        base_url="https://api.deepseek.com",
        temperature=0,
    ).with_structured_output(RelevanceLabels, method="function_calling")
    reviewed = {}
    if args.output.exists():
        reviewed = {
            row["id"]: row
            for row in load_cases(args.output)
            if row.get("label_quality") == "silver_reviewed"
        }

    labelled = []
    for index, case in enumerate(cases, start=1):
        if case["id"] in reviewed:
            labelled.append(reviewed[case["id"]])
            print(f"kept reviewed {index}/{len(cases)}: {case['id']}")
            continue
        if not case["reference_qids"]:
            labelled.append({
                **case,
                "reference_answer": "该问题不属于当前社区技术知识库，资料不足，无法回答。",
                "label_quality": "silver",
                "label_confidence": 1.0,
                "label_reason": "人工定义的库外负样本",
            })
            continue
        candidates = candidate_documents(case["user_input"])
        rendered = "\n\n".join(
            f"qid={doc['qid']} 标题={doc['title']}\n{doc['content'][:700]}"
            for doc in candidates
        )
        verdict = judge.invoke(
            "你在为中文 RAG 检索建立严格银标。请选出能够直接回答用户问题的最小充分文档集合。"
            "优先一篇最直接的文档；只有单篇确实缺少必要事实时才增加其他文档。"
            "严禁因为属于同一大主题、共享关键词、提供一般性预防建议或仅有间接关系就选入。"
            "例如缓存穿透问题不能加入击穿、雪崩或缓存预热文档。不得输出候选之外的 qid。"
            "reference_answer 必须简洁覆盖问题核心，只能使用所选文档支持的事实，不要复述问题或资料标题。\n\n"
            f"用户问题：{case['user_input']}\n\n候选文档：\n{rendered}"
        )
        allowed = {doc["qid"] for doc in candidates}
        selected = sorted(set(verdict.relevant_qids) & allowed)
        labelled.append({
            **case,
            "reference_qids": selected,
            "reference_answer": verdict.reference_answer,
            "label_quality": "silver",
            "label_confidence": verdict.confidence,
            "label_reason": verdict.reason,
            "candidate_qids": sorted(allowed),
        })
        print(f"labelled {index}/{len(cases)}: {case['id']} -> {selected}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as target:
        for row in labelled:
            target.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"saved: {args.output}")


if __name__ == "__main__":
    main()
