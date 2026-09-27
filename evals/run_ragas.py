from __future__ import annotations

import argparse
import asyncio
import json
import statistics
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI
from ragas.embeddings import BaseRagasEmbedding
from ragas.llms import llm_factory
from ragas.metrics.collections import (
    AnswerRelevancy,
    ContextPrecision,
    ContextRecall,
    FactualCorrectness,
    Faithfulness,
)

from app.core.config import settings
from app.core.rag import embeddings as project_embeddings


class ProjectEmbeddingAdapter(BaseRagasEmbedding):
    """Expose the project's offline LangChain embeddings via Ragas' modern API."""

    def embed_text(self, text: str, **kwargs: Any) -> list[float]:
        return project_embeddings.embed_query(text)

    async def aembed_text(self, text: str, **kwargs: Any) -> list[float]:
        return await asyncio.to_thread(project_embeddings.embed_query, text)

    def embed_texts(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
        return project_embeddings.embed_documents(texts)

    async def aembed_texts(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
        return await asyncio.to_thread(project_embeddings.embed_documents, texts)


def _fatal_provider_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "insufficient balance" in message or "error code: 402" in message


async def score_row(row: dict, scorers: dict, existing: dict | None = None) -> tuple[dict, str | None]:
    values = {
        "user_input": row["user_input"],
        "response": row["response"],
        "retrieved_contexts": row["retrieved_contexts"],
        "reference": row["reference"],
    }
    required = {
        "faithfulness": ("user_input", "response", "retrieved_contexts"),
        "factual_correctness": ("response", "reference"),
        "response_relevancy": ("user_input", "response"),
        "context_precision": ("user_input", "reference", "retrieved_contexts"),
        "context_recall": ("user_input", "retrieved_contexts", "reference"),
    }
    scores = dict((existing or {}).get("ragas") or {})
    errors = dict((existing or {}).get("ragas_errors") or {})
    for name in scorers:
        scores.setdefault(name, None)
    fatal_error = None
    for name, scorer in scorers.items():
        if scores.get(name) is not None:
            errors.pop(name, None)
            continue
        inputs = {key: values[key] for key in required[name]}
        try:
            result = await scorer.ascore(**inputs)
            scores[name] = result.value
            errors.pop(name, None)
        except Exception as exc:  # preserve the rest of an expensive evaluation batch
            scores[name] = None
            errors[name] = f"{type(exc).__name__}: {exc}"
            if _fatal_provider_error(exc):
                fatal_error = errors[name]
                break
    return {**row, "ragas": scores, "ragas_errors": errors}, fatal_error


async def run(input_path: Path, output_path: Path, resume: bool = False) -> None:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    rows = payload["rows"] if isinstance(payload, dict) else payload
    # Ragas context metrics require a positive reference. Out-of-domain refusal
    # is evaluated deterministically by run_custom_judge.py instead.
    rows = [row for row in rows if row["reference_qids"]]
    client = AsyncOpenAI(api_key=settings.DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")
    evaluator_llm = llm_factory(
        "deepseek-chat", provider="openai", client=client, max_tokens=8192
    )
    # Reuse the project's already cached offline embedding model. Constructing
    # Ragas' own HuggingFace wrapper probes the network even when weights exist.
    evaluator_embeddings = ProjectEmbeddingAdapter()
    scorers = {
        "faithfulness": Faithfulness(llm=evaluator_llm),
        "factual_correctness": FactualCorrectness(llm=evaluator_llm),
        "response_relevancy": AnswerRelevancy(llm=evaluator_llm, embeddings=evaluator_embeddings),
        "context_precision": ContextPrecision(llm=evaluator_llm),
        "context_recall": ContextRecall(llm=evaluator_llm),
    }
    existing_by_id = {}
    if resume:
        if not output_path.exists():
            raise ValueError(f"checkpoint does not exist: {output_path}")
        checkpoint = json.loads(output_path.read_text(encoding="utf-8"))
        existing_rows = checkpoint.get("rows", []) if isinstance(checkpoint, dict) else []
        existing_by_id = {row["id"]: row for row in existing_rows}
        if len(existing_by_id) != len(existing_rows):
            raise ValueError(f"{output_path} contains duplicate case ids")

    scored = []
    output_path.parent.mkdir(parents=True, exist_ok=True)
    for index, row in enumerate(rows, start=1):
        existing = existing_by_id.get(row["id"])
        if existing and (
            existing.get("user_input") != row.get("user_input")
            or existing.get("response") != row.get("response")
        ):
            raise ValueError(f"{row['id']}: checkpoint input or response changed")
        result, fatal_error = await score_row(row, scorers, existing)
        scored.append(result)
        available = {
            name: [item["ragas"][name] for item in scored if item["ragas"][name] is not None]
            for name in scorers
        }
        summary = {
            name: (statistics.fmean(values) if values else None)
            for name, values in available.items()
        }
        summary["sample_count"] = len(scored)
        summary["metric_sample_counts"] = {
            name: len(values) for name, values in available.items()
        }
        summary["rows_with_errors"] = sum(bool(item["ragas_errors"]) for item in scored)
        output_path.write_text(
            json.dumps({"summary": summary, "rows": scored}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"scored {index}/{len(rows)}: {row['id']}")
        if fatal_error:
            raise RuntimeError(f"fatal evaluator error at {row['id']}: {fatal_error}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Score collected RAG answers with Ragas.")
    parser.add_argument("input", type=Path, help="JSON produced by the answer collector")
    parser.add_argument("--output", type=Path, default=Path("evals/results/ragas.json"))
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Reuse successful per-metric scores from an existing --output checkpoint.",
    )
    args = parser.parse_args()
    asyncio.run(run(args.input, args.output, resume=args.resume))


if __name__ == "__main__":
    main()
