import asyncio

from evals.run_ragas import _fatal_provider_error, score_row


class _Result:
    def __init__(self, value):
        self.value = value


class _Scorer:
    def __init__(self, value):
        self.value = value
        self.calls = 0

    async def ascore(self, **kwargs):
        self.calls += 1
        return _Result(self.value)


class _FailingScorer:
    async def ascore(self, **kwargs):
        raise RuntimeError("Error code: 402 - Insufficient Balance")


def test_score_row_reuses_existing_metric_and_fills_missing_one():
    faithfulness = _Scorer(0.9)
    factual = _Scorer(0.8)
    row = {
        "id": "in_01",
        "user_input": "question",
        "response": "answer",
        "retrieved_contexts": ["context"],
        "reference": "reference",
    }
    existing = {
        "ragas": {"faithfulness": 0.7, "factual_correctness": None},
        "ragas_errors": {"factual_correctness": "old error"},
    }

    result, fatal = asyncio.run(
        score_row(
            row,
            {"faithfulness": faithfulness, "factual_correctness": factual},
            existing,
        )
    )

    assert fatal is None
    assert result["ragas"] == {"faithfulness": 0.7, "factual_correctness": 0.8}
    assert result["ragas_errors"] == {}
    assert faithfulness.calls == 0
    assert factual.calls == 1


def test_insufficient_balance_is_fatal():
    assert _fatal_provider_error(RuntimeError("Error code: 402 - Insufficient Balance"))


def test_fatal_error_leaves_unattempted_metric_keys_as_none():
    row = {
        "id": "in_01",
        "user_input": "question",
        "response": "answer",
        "retrieved_contexts": ["context"],
        "reference": "reference",
    }

    result, fatal = asyncio.run(
        score_row(
            row,
            {"faithfulness": _FailingScorer(), "factual_correctness": _Scorer(0.8)},
        )
    )

    assert "Insufficient Balance" in fatal
    assert result["ragas"] == {"faithfulness": None, "factual_correctness": None}
