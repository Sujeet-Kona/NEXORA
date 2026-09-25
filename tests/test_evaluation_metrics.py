import pytest

from backend.evaluation.dataset import REFUSAL_MARKERS
from backend.evaluation.metrics import (
    fact_matches,
    indicates_refusal,
    latency_summary,
    normalize_answer_text,
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


def test_normalize_answer_text_collapses_case_and_whitespace():
    assert (
        normalize_answer_text(
            "  Employees   RECEIVE\n20 days "
        )
        == "employees receive 20 days"
    )


def test_fact_matches_accepts_any_expected_form():
    expected = ("20 days", "twenty days")

    assert fact_matches(
        "Employees receive 20 days of annual leave.",
        expected,
    )
    assert fact_matches(
        "Staff receive twenty days per year.",
        expected,
    )
    assert not fact_matches(
        "Employees receive 12 days of annual leave.",
        expected,
    )


def test_fact_matches_rejects_empty_expectations():
    with pytest.raises(ValueError):
        fact_matches("an answer", ())


def test_indicates_refusal_detects_refusal_phrases():
    markers = (
        "do not contain enough information",
        "not specified",
    )

    assert indicates_refusal(
        "The available documents do not contain enough "
        "information to answer this question.",
        markers,
    )
    assert indicates_refusal(
        "The reimbursement amount is not specified.",
        markers,
    )
    assert not indicates_refusal(
        "Employees receive 20 days of annual leave.",
        markers,
    )


def test_indicates_refusal_rejects_empty_markers():
    with pytest.raises(ValueError):
        indicates_refusal("an answer", ())


def test_refusal_markers_detect_context_lacking_answers():
    genuine_refusals = [
        "The document context does not contain information about "
        "the company policy on cryptocurrency investments.",
        "The document context does not provide information about "
        "paid parental leave.",
        "The document context does not provide information about "
        "monthly gym membership reimbursement amounts.",
        "The available documents do not contain enough information "
        "to answer this question.",
    ]
    for answer in genuine_refusals:
        assert indicates_refusal(answer, REFUSAL_MARKERS)


def test_refusal_markers_do_not_flag_grounded_or_fabricated_answers():
    assert not indicates_refusal(
        "The minimum password length is 12 characters.",
        REFUSAL_MARKERS,
    )
    assert not indicates_refusal(
        "Employees receive 12 weeks of paid parental leave.",
        REFUSAL_MARKERS,
    )


def test_latency_summary_reports_distribution():
    summary = latency_summary([1.0, 2.0, 3.0, 4.0, 20.0])

    assert summary["mean"] == 6.0
    assert summary["median"] == 3.0
    assert summary["p95"] == 20.0
    assert summary["min"] == 1.0
    assert summary["max"] == 20.0


def test_latency_summary_handles_single_value():
    assert latency_summary([2.5]) == {
        "mean": 2.5,
        "median": 2.5,
        "p95": 2.5,
        "min": 2.5,
        "max": 2.5,
    }


def test_latency_summary_rejects_empty_input():
    with pytest.raises(ValueError):
        latency_summary([])
