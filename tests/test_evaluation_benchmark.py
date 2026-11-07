import pytest

from backend.evaluation.benchmark import evaluate_context_coverage


def test_evaluate_context_coverage_reports_recall_hits_and_empty_contexts():
    result = evaluate_context_coverage(
        rankings=[[1, 3], [4], []],
        ground_truths=[{1, 2}, {2}, {3}],
        context_limit=2,
    )

    assert result["context_limit"] == 2
    assert result["context_recall"] == pytest.approx(1 / 6)
    assert result["context_hit_rate"] == pytest.approx(1 / 3)
    assert result["empty_context_rate"] == pytest.approx(1 / 3)
    assert result["mean_context_chunks"] == pytest.approx(1.0)


def test_evaluate_context_coverage_rejects_invalid_limit_or_alignment():
    with pytest.raises(ValueError):
        evaluate_context_coverage([[1]], [{1}], 0)

    with pytest.raises(ValueError):
        evaluate_context_coverage([[1]], [], 1)

    with pytest.raises(ValueError):
        evaluate_context_coverage([[1], [2]], [{1}], 1)
