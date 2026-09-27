from __future__ import annotations

import argparse
import json
import re
import statistics
from pathlib import Path

_KB_TOOLS = {"search_master", "search_live_questions", "get_answers"}
_READ_TOOLS = _KB_TOOLS | {"get_weather", "get_time", "get_location"}


def score_tool_routing(row: dict) -> dict:
    tool_calls = row.get("tool_calls") or [
        {"name": name, "args": {}} for name in row.get("called_tools", [])
    ]
    called_in_order = [call.get("name", "") for call in tool_calls]
    called = set(called_in_order)
    in_domain = bool(row.get("reference_qids"))
    default_required = {"search_master"} if in_domain else set()
    if row.get("id") == "out_01":
        default_required = {"get_weather"}
    required = set(row.get("required_tools", default_required))
    default_allowed = required if not in_domain else {"search_master"}
    allowed = set(row.get("allowed_tools", default_allowed))
    forbidden = _READ_TOOLS - allowed
    missing = sorted(required - called)
    unexpected = sorted(forbidden & called)
    signatures = [
        f"{call.get('name', '')}:{json.dumps(call.get('args') or {}, sort_keys=True, ensure_ascii=False)}"
        for call in tool_calls
    ]
    duplicates = sorted({signature for signature in signatures if signatures.count(signature) > 1})

    parameter_errors = []
    search_index = next(
        (index for index, name in enumerate(called_in_order) if name == "search_master"),
        None,
    )
    retrieved_qids = {str(qid) for qid in row.get("retrieved_context_ids", [])}
    for index, call in enumerate(tool_calls):
        if call.get("name") != "get_answers":
            continue
        question_id = (call.get("args") or {}).get("question_id")
        if type(question_id) is not int or question_id <= 0:
            parameter_errors.append("get_answers question_id must be a positive integer")
            continue
        user_supplied_qids = set(re.findall(r"(?i)qid\s*[=:：]?\s*(\d+)", row.get("user_input", "")))
        follows_search = search_index is not None and search_index < index
        if follows_search and str(question_id) in retrieved_qids:
            continue
        if str(question_id) in user_supplied_qids:
            continue
        parameter_errors.append(
            "get_answers question_id must come from earlier search results or explicit user input"
        )

    correct = not missing and not unexpected and not duplicates and not parameter_errors
    return {
        "routing_correct": float(correct),
        "required_tools": sorted(required),
        "allowed_tools": sorted(allowed),
        "missing_tools": missing,
        "forbidden_tools": sorted(forbidden),
        "unexpected_tools": unexpected,
        "duplicate_tool_calls": duplicates,
        "parameter_errors": parameter_errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Score deterministic Agent tool-routing rules.")
    parser.add_argument("inputs", type=Path, nargs="+")
    parser.add_argument(
        "--output", type=Path, default=Path("evals/results/tool_routing.json")
    )
    args = parser.parse_args()
    rows = []
    for input_path in args.inputs:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
        rows.extend(payload["rows"] if isinstance(payload, dict) else payload)
    scored = [{**row, "tool_routing": score_tool_routing(row)} for row in rows]
    values = [row["tool_routing"]["routing_correct"] for row in scored]
    in_domain = [row for row in scored if row.get("reference_qids")]
    out_of_domain = [row for row in scored if not row.get("reference_qids")]

    def mean(group: list[dict]) -> float | None:
        if not group:
            return None
        return statistics.fmean(row["tool_routing"]["routing_correct"] for row in group)

    result = {
        "summary": {
            "sample_count": len(scored),
            "routing_accuracy": statistics.fmean(values) if values else None,
            "in_domain_routing_accuracy": mean(in_domain),
            "out_of_domain_routing_accuracy": mean(out_of_domain),
        },
        "rows": scored,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    print(f"saved: {args.output}")


if __name__ == "__main__":
    main()
