import math

import pytest

from evals.metrics import (
    correct_abstention,
    hit_at_k,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)


def test_rank_metrics_use_document_ids():
    retrieved = ["9", "2", "3"]
    relevant = [2, 4]
    assert precision_at_k(retrieved, relevant, 3) == pytest.approx(1 / 3)
    assert recall_at_k(retrieved, relevant, 3) == pytest.approx(1 / 2)
    assert hit_at_k(retrieved, relevant, 1) == 0.0
    assert hit_at_k(retrieved, relevant, 3) == 1.0
    assert reciprocal_rank(retrieved, relevant) == pytest.approx(1 / 2)
    ideal_dcg = 1 + 1 / math.log2(3)
    assert ndcg_at_k(retrieved, relevant, 3) == pytest.approx((1 / math.log2(3)) / ideal_dcg)


def test_out_of_domain_is_scored_as_abstention_not_recall():
    assert math.isnan(recall_at_k([], [], 3))
    assert correct_abstention([], []) == 1.0
    assert correct_abstention(["1"], []) == 0.0


def test_invalid_k_is_rejected():
    with pytest.raises(ValueError):
        recall_at_k([], [1], 0)
