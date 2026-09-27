from __future__ import annotations

import math
from collections.abc import Iterable, Sequence


def _ids(values: Iterable[object]) -> list[str]:
    return [str(value) for value in values]


def precision_at_k(retrieved: Sequence[object], relevant: Sequence[object], k: int) -> float:
    """Binary precision in the first k ranks.

    The denominator is k so returning fewer than k results is treated as unused
    retrieval capacity instead of receiving an artificially perfect score.
    """
    if k <= 0:
        raise ValueError("k must be positive")
    relevant_set = set(_ids(relevant))
    hits = sum(item in relevant_set for item in _ids(retrieved)[:k])
    return hits / k


def recall_at_k(retrieved: Sequence[object], relevant: Sequence[object], k: int) -> float:
    if k <= 0:
        raise ValueError("k must be positive")
    relevant_set = set(_ids(relevant))
    if not relevant_set:
        return math.nan
    return len(set(_ids(retrieved)[:k]) & relevant_set) / len(relevant_set)


def hit_at_k(retrieved: Sequence[object], relevant: Sequence[object], k: int) -> float:
    if k <= 0:
        raise ValueError("k must be positive")
    relevant_set = set(_ids(relevant))
    if not relevant_set:
        return math.nan
    return float(bool(set(_ids(retrieved)[:k]) & relevant_set))


def reciprocal_rank(retrieved: Sequence[object], relevant: Sequence[object]) -> float:
    relevant_set = set(_ids(relevant))
    for rank, item in enumerate(_ids(retrieved), start=1):
        if item in relevant_set:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(retrieved: Sequence[object], relevant: Sequence[object], k: int) -> float:
    if k <= 0:
        raise ValueError("k must be positive")
    relevant_set = set(_ids(relevant))
    if not relevant_set:
        return math.nan
    dcg = sum(
        1.0 / math.log2(rank + 1)
        for rank, item in enumerate(_ids(retrieved)[:k], start=1)
        if item in relevant_set
    )
    ideal_hits = min(k, len(relevant_set))
    idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
    return dcg / idcg


def correct_abstention(retrieved: Sequence[object], relevant: Sequence[object]) -> float:
    """Score only out-of-domain examples: 1 when no document is returned."""
    if relevant:
        return math.nan
    return float(not retrieved)
