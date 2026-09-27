from __future__ import annotations

import argparse
import json
import re
import time
import uuid
from datetime import datetime
from pathlib import Path

from langchain_core.messages import HumanMessage

from app.core.config import settings
from app.routers.ai import _build_agent, _new_guard
from evals.dataset import hydrate_references, load_cases

_QID = re.compile(r"qid:(\d+)")
_CONTEXT_BLOCK = re.compile(
    r"(?ms)\[资料\d+\].*?(?=^\[资料\d+\]|</untrusted_tool_data>|\Z)"
)
_EVIDENCE_TOOLS = {"search_master", "search_live_questions", "get_answers"}


def _text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            item.get("text", "") if isinstance(item, dict) else str(item)
            for item in content
        )
    return str(content)


def context_blocks(text: str) -> list[str]:
    blocks = [block.strip() for block in _CONTEXT_BLOCK.findall(text)]
    return blocks or ([text] if text else [])


def load_checkpoint(output: Path, case_ids: set[str]) -> tuple[dict, list[dict]]:
    payload = json.loads(output.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("rows"), list):
        raise ValueError(f"{output} is not a valid answer checkpoint")
    rows = payload["rows"]
    completed_ids = [row.get("id") for row in rows]
    if len(set(completed_ids)) != len(completed_ids):
        raise ValueError(f"{output} contains duplicate case ids")
    unknown = set(completed_ids) - case_ids
    if unknown:
        raise ValueError(f"{output} contains unknown case ids: {sorted(unknown)}")
    return payload.get("metadata") or {}, rows


def collect_case(agent, guard, case: dict) -> dict:
    started = time.perf_counter()
    result = agent.invoke(
        {"messages": [HumanMessage(content=case["user_input"])]},
        config={"configurable": {"thread_id": f"eval-{uuid.uuid4()}"}, "recursion_limit": 30},
    )
    latency_ms = (time.perf_counter() - started) * 1000
    messages = result.get("messages", [])
    tool_calls = []
    for message in messages:
        if getattr(message, "type", "") != "ai":
            continue
        for call in getattr(message, "tool_calls", []) or []:
            tool_calls.append({
                "name": call.get("name", ""),
                "args": call.get("args", {}),
                "id": call.get("id", ""),
            })
    tool_messages = [message for message in messages if getattr(message, "type", "") == "tool"]
    called_tools = [getattr(message, "name", "") for message in tool_messages]
    prepared_tools = guard.prepare_messages(tool_messages)
    evidence_texts = [
        _text(message.content)
        for message in prepared_tools
        if getattr(message, "name", "") in _EVIDENCE_TOOLS
    ]
    search_texts = [
        _text(message.content)
        for message in tool_messages
        if getattr(message, "name", "") == "search_master"
    ]
    contexts = []
    for text in evidence_texts:
        contexts.extend(context_blocks(text))
    retrieved_qids = _QID.findall("\n".join(search_texts))
    ai_messages = [message for message in messages if getattr(message, "type", "") == "ai"]
    response = _text(ai_messages[-1].content) if ai_messages else ""
    return {
        **case,
        "response": response,
        "retrieved_contexts": contexts,
        "retrieved_context_ids": list(dict.fromkeys(retrieved_qids)),
        "called_tools": called_tools,
        "tool_calls": tool_calls,
        "latency_ms": round(latency_ms, 2),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect answers from the real anonymous Agent path.")
    parser.add_argument("--input", type=Path, help="Optional JSONL case file.")
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--ids",
        nargs="+",
        help="Only collect the listed case ids (for example: out_01 out_02).",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Continue an existing --output checkpoint and skip completed case ids.",
    )
    args = parser.parse_args()
    if args.resume and args.output is None:
        parser.error("--resume requires --output")
    cases = hydrate_references(load_cases(args.input))
    if args.ids:
        wanted = set(args.ids)
        cases = [case for case in cases if case["id"] in wanted]
        missing = wanted - {case["id"] for case in cases}
        if missing:
            parser.error(f"unknown case ids: {', '.join(sorted(missing))}")
    if args.limit:
        cases = cases[: args.limit]

    output = args.output or Path("evals/results") / f"answers_{datetime.now():%Y%m%d_%H%M%S}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    metadata = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "generator_model": settings.LLM_GATEWAY_MODEL,
        "label_quality": "silver",
    }
    rows = []
    if args.resume:
        if not output.exists():
            parser.error(f"checkpoint does not exist: {output}")
        try:
            metadata, rows = load_checkpoint(output, {case["id"] for case in cases})
        except ValueError as exc:
            parser.error(str(exc))
        completed = {row["id"] for row in rows}
        cases = [case for case in cases if case["id"] not in completed]
        print(f"resuming: {len(rows)} completed, {len(cases)} remaining")

    if not cases:
        print(f"already complete: {output}")
        return

    guard = _new_guard()
    agent = _build_agent(None, guard)
    total = len(rows) + len(cases)
    for case in cases:
        row = collect_case(agent, guard, case)
        rows.append(row)
        output.write_text(json.dumps({"metadata": metadata, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"collected {len(rows)}/{total}: {case['id']} tools={row['called_tools']}")
    print(f"saved: {output}")


if __name__ == "__main__":
    main()
