import pytest

from backend.evaluation.dataset import REFUSAL_MARKERS
from backend.evaluation.metrics import (
    fact_matches,
    citation_indices,
    citations_are_valid_and_grounded,
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
def reciprocal_rank(
    relevant: set[int],
    retrieved: list[int],
) -> float:
    for rank, chunk_id in enumerate(retrieved, start=1):
        if chunk_id in relevant:
            return 1.0 / rank

    return 0.0

def average_precision_at_k(
    relevant: set[int],
    retrieved: list[int],
    k: int,
) -> float:
    """Single-query AP@K in canonical BEIR style.

    Sums precision@i for each position i where a relevant document is
    retrieved, then divides by the TOTAL relevant count (not the number
    retrieved). Used later to compute MAP@K across the full 30-question
    evaluation set.
    """
    if k < 1:
        raise ValueError("k must be at least 1")
    if not relevant:
        raise ValueError("relevant must be non-empty")

    hits = 0.0
    precision_sum = 0.0

    for i, chunk_id in enumerate(retrieved[:k], start=1):
        if chunk_id in relevant:
            hits += 1.0
            precision_sum += hits / i

    return precision_sum / len(relevant)

def mean_reciprocal_rank(
    queries: list[tuple[set[int], list[int]]],
) -> float:
    """MRR across a list of (relevant_set, retrieved_list) queries."""
    if not queries:
        raise ValueError("queries must be non-empty")

    return (
        sum(
            reciprocal_rank(relevant, retrieved)
            for relevant, retrieved in queries
        )
        / len(queries)
    )

class CitationSource:
    def __init__(self, chunk_id):
        self.chunk_id = chunk_id


def test_citation_indices_extract_unique_indices_in_order():
    assert citation_indices("Fact [2], more [1], repeated [2].") == [2, 1]


def test_citations_require_valid_index_and_relevant_source():
    sources = [
        CitationSource(10),
        CitationSource(20),
    ]

    assert citations_are_valid_and_grounded(
        "Supported fact [2].",
        sources,
        {20},
    )

    assert not citations_are_valid_and_grounded(
        "Supported fact.",
        sources,
        {20},
    )

    assert not citations_are_valid_and_grounded(
        "Unsupported citation [3].",
        sources,
        {20},
    )

    assert not citations_are_valid_and_grounded(
        "Cites the wrong source [1].",
        sources,
        {20},
    )
