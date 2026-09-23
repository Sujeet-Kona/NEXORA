import pytest

from backend.evaluation.metrics import (
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)


def test_recall_at_k():
    relevant = {1, 2}
    retrieved = [1, 3, 2, 4]

    assert recall_at_k(relevant, retrieved, 1) == 0.5
    assert recall_at_k(relevant, retrieved, 3) == 1.0
    assert recall_at_k(relevant, retrieved, 10) == 1.0


def test_recall_at_k_with_no_hits():
    assert recall_at_k({1, 2}, [5, 6], 5) == 0.0
    assert recall_at_k({1}, [], 5) == 0.0


def test_recall_at_k_rejects_invalid_arguments():
    with pytest.raises(ValueError):
        recall_at_k(set(), [1, 2], 5)

    with pytest.raises(ValueError):
        recall_at_k({1}, [1], 0)


def test_precision_at_k():
    relevant = {1, 2}
    retrieved = [1, 3, 2, 4]

    assert precision_at_k(relevant, retrieved, 1) == 1.0
    assert precision_at_k(relevant, retrieved, 2) == 0.5
    assert precision_at_k(relevant, retrieved, 10) == 0.2


def test_precision_at_k_with_no_hits():
    assert precision_at_k({1, 2}, [5, 6], 5) == 0.0
    assert precision_at_k({1}, [], 5) == 0.0


def test_precision_at_k_rejects_invalid_k():
    with pytest.raises(ValueError):
        precision_at_k({1}, [1], 0)


def test_reciprocal_rank():
    assert reciprocal_rank({1, 2}, [3, 1, 2]) == 0.5
    assert reciprocal_rank({1}, [1, 2, 3]) == 1.0
    assert reciprocal_rank({1, 2}, [5, 6]) == 0.0
    assert reciprocal_rank({1}, []) == 0.0
