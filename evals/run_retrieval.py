from __future__ import annotations

import argparse
import json
import math
import statistics
import time
import warnings
from datetime import datetime
from pathlib import Path

from app.core import rag
from evals.dataset import hydrate_references, load_cases
from evals.metrics import (
    correct_abstention,
    hit_at_k,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)


def _qids(hits: list[dict]) -> list[str]:
    return [str(hit.get("source", {}).get("qid")) for hit in hits if hit.get("source", {}).get("qid") is not None]


def _mean(rows: list[dict], key: str) -> float | None:
    values = [row[key] for row in rows if not math.isnan(row[key])]
    return statistics.fmean(values) if values else None


def evaluate_case(case: dict, use_bm25: bool) -> dict:
    query = case["user_input"]
    rag.redis_client.delete(rag._cache_key(query))

    started = time.perf_counter()
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Relevance scores must be between 0 and 1")
        vector_docs = rag.vectorstore.similarity_search_with_relevance_scores(query, k=rag._RETRIEVAL_TOP_K)
    vector_ms = (time.perf_counter() - started) * 1000
    vector_qids = [str(doc.metadata.get("qid")) for doc, _ in vector_docs if doc.metadata.get("qid") is not None]

    started = time.perf_counter()
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Relevance scores must be between 0 and 1")
        ranked_hits = rag.search(query, top_k=rag._RERANK_TOP_K, use_bm25=use_bm25)
    ranked_ms = (time.perf_counter() - started) * 1000
    ranked_qids = _qids(ranked_hits)
    reference_qids = [str(qid) for qid in case["reference_qids"]]

    return {
        **case,
        "retrieved_context_ids": ranked_qids,
        "retrieved_contexts": [hit["content"] for hit in ranked_hits[:3]],
        "vector_context_ids": vector_qids,
        "recall_at_1": recall_at_k(ranked_qids, reference_qids, 1),
        "recall_at_3": recall_at_k(ranked_qids, reference_qids, 3),
        "recall_at_8": recall_at_k(ranked_qids, reference_qids, 8),
        "hit_at_1": hit_at_k(ranked_qids, reference_qids, 1),
        "hit_at_3": hit_at_k(ranked_qids, reference_qids, 3),
        "hit_at_8": hit_at_k(ranked_qids, reference_qids, 8),
        "precision_at_3": precision_at_k(ranked_qids, reference_qids, 3),
        "mrr_at_8": reciprocal_rank(ranked_qids[:8], reference_qids),
        "ndcg_at_3": ndcg_at_k(ranked_qids, reference_qids, 3),
        "vector_recall_at_50": recall_at_k(vector_qids, reference_qids, 50),
        "correct_abstention": correct_abstention(ranked_qids, reference_qids),
        "vector_latency_ms": round(vector_ms, 2),
        "ranking_latency_ms": round(ranked_ms, 2),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("hybrid", "vector"), default="hybrid")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    cases = hydrate_references(load_cases())
    if args.limit:
        cases = cases[: args.limit]
    rows = [evaluate_case(case, use_bm25=args.mode == "hybrid") for case in cases]
    in_domain = [row for row in rows if row["reference_qids"]]
    out_of_domain = [row for row in rows if not row["reference_qids"]]
    summary = {
        "mode": args.mode,
        "sample_count": len(rows),
        "in_domain_count": len(in_domain),
        "out_of_domain_count": len(out_of_domain),
        **{key: _mean(in_domain, key) for key in (
            "recall_at_1", "recall_at_3", "recall_at_8",
            "hit_at_1", "hit_at_3", "hit_at_8", "precision_at_3",
            "mrr_at_8", "ndcg_at_3", "vector_recall_at_50",
        )},
        "correct_abstention_rate": _mean(out_of_domain, "correct_abstention"),
        "mean_vector_latency_ms": statistics.fmean(row["vector_latency_ms"] for row in rows),
        "mean_ranking_latency_ms": statistics.fmean(row["ranking_latency_ms"] for row in rows),
    }
    output = args.output or Path("evals/results") / f"retrieval_{args.mode}_{datetime.now():%Y%m%d_%H%M%S}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    serializable_rows = [
        {key: (None if isinstance(value, float) and math.isnan(value) else value) for key, value in row.items()}
        for row in rows
    ]
    output.write_text(json.dumps({"summary": summary, "rows": serializable_rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"saved: {output}")


if __name__ == "__main__":
    main()
