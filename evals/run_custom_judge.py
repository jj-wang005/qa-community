from __future__ import annotations

import argparse
import json
import math
import re
import statistics
from pathlib import Path

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from app.core.config import settings


class CompletenessVerdict(BaseModel):
    completeness: int = Field(ge=0, le=10)
    reason: str


def _normalise_title(title: str) -> str:
    return re.sub(r"[\s？?。！!]+$", "", title.strip())


def _citation_score(row: dict) -> float:
    if not row["reference_qids"]:
        return math.nan
    cited_groups = re.findall(r"（来源：([^）]+)）", row["response"])
    cited = [
        _normalise_title(title)
        for group in cited_groups
        for title in re.split(r"[；;、]", group)
        if title.strip()
    ]
    if not cited:
        return 0.0
    known_titles = {
        _normalise_title(match.group(1))
        for context in row["retrieved_contexts"]
        for match in re.finditer(r"来源：(.+?)(?:\s*\(qid:|\n)", context)
    }
    return float(bool(known_titles) and all(title in known_titles for title in cited))


def _refusal_score(row: dict) -> float:
    if row["reference_qids"]:
        return math.nan
    if any(
        tool not in {"search_master", "search_live_questions", "get_answers"}
        for tool in row.get("called_tools", [])
    ):
        return math.nan
    response = row["response"]
    refusal = re.search(
        r"资料不足|无法回答|无法确认|不能确认|没有相关资料|没有找到|未找到|"
        r"不支持|不在.{0,12}范围|不属于.{0,20}范围|超出.{0,12}范围|"
        r"没有相关工具|当前没有.{0,12}工具|无法提供|无法查询",
        response,
    )
    unsupported_continuation = re.search(
        r"不过.{0,20}(?:基于|可以).{0,20}(?:常识|经验|建议)|"
        r"以下是一些(?:通用|基本|具体).{0,10}(?:建议|方法|步骤)",
        response,
        re.DOTALL,
    )
    return float(bool(refusal) and not unsupported_continuation)


def main() -> None:
    parser = argparse.ArgumentParser(description="Project-specific judge; complements Ragas.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, default=Path("evals/results/custom_judge.json"))
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    rows = payload["rows"] if isinstance(payload, dict) else payload

    judge = ChatOpenAI(
        model="deepseek-chat",
        api_key=settings.DEEPSEEK_API_KEY,
        base_url="https://api.deepseek.com",
        temperature=0,
    ).with_structured_output(CompletenessVerdict, method="function_calling")

    scored = []
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for index, row in enumerate(rows, start=1):
        verdict = judge.invoke(
            "你只评估回答完整性，不评估事实忠实性或相关性。"
            "对照参考答案，判断回答是否覆盖问题需要的关键要点。"
            "0 表示完全没有回答，10 表示关键要点完整。\n\n"
            f"问题：{row['user_input']}\n\n"
            f"参考答案（银标）：{row['reference']}\n\n"
            f"待评回答：{row['response']}"
        )
        scored.append({
            **row,
            "custom_judge": {
                "completeness": verdict.completeness,
                "completeness_reason": verdict.reason,
                "citation_valid": _citation_score(row),
                "correct_refusal": _refusal_score(row),
                "used_search_master": "search_master" in row.get("called_tools", []),
            },
        })
        summary = {
            "sample_count": len(scored),
            "completeness": statistics.fmean(item["custom_judge"]["completeness"] for item in scored),
        }
        args.output.write_text(
            json.dumps({"summary": summary, "rows": scored}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"judged {index}/{len(rows)}: {row['id']}")


if __name__ == "__main__":
    main()
