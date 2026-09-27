from __future__ import annotations

import json
from pathlib import Path

from app.db.base import SessionLocal
from app.models.answer import Answer
from app.models.question import Question

ROOT = Path(__file__).resolve().parent
DEFAULT_CASES = ROOT / "data" / "cases.jsonl"
SILVER_CASES = ROOT / "data" / "cases_silver.jsonl"


def load_cases(path: Path | None = None) -> list[dict]:
    path = path or (SILVER_CASES if SILVER_CASES.exists() else DEFAULT_CASES)
    rows = []
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            required = {"id", "type", "user_input", "reference_qids"}
            missing = required - row.keys()
            if missing:
                raise ValueError(f"{path}:{line_number} missing {sorted(missing)}")
            rows.append(row)
    if len({row["id"] for row in rows}) != len(rows):
        raise ValueError("case ids must be unique")
    return rows


def hydrate_references(cases: list[dict]) -> list[dict]:
    """Attach a reproducible silver reference from the current qid documents.

    The accepted/highest-liked answer selected by the production KB builder is
    used as the reference. This is intentionally labelled silver, not human gold.
    """
    db = SessionLocal()
    try:
        hydrated = []
        for case in cases:
            documents = []
            for qid in case["reference_qids"]:
                question = db.get(Question, int(qid))
                if question is None:
                    raise ValueError(f"{case['id']}: qid {qid} does not exist")
                answer = (
                    db.query(Answer)
                    .filter(Answer.question_id == question.id)
                    .order_by(Answer.is_accepted.desc(), Answer.like_count.desc(), Answer.id.asc())
                    .first()
                )
                text = f"问题：{question.title}\n{question.content}"
                if answer:
                    text += f"\n回答：{answer.content[:500]}"
                documents.append(text)
            reference = case.get("reference_answer") or (
                "\n\n".join(documents) if documents else "资料不足，无法回答。"
            )
            hydrated.append({
                **case,
                "reference_contexts": documents,
                "reference": reference,
                "label_quality": "silver",
            })
        return hydrated
    finally:
        db.close()
