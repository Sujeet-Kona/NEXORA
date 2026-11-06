import json

import pytest

from backend.evaluation.human_review import (
    load_reviews,
    summarize_reviews,
    validate_review,
)


def make_review(case_id="case-1", reviewer_id="reviewer-1", **overrides):
    review = {
        "case_id": case_id,
        "reviewer_id": reviewer_id,
        "question": "How many leave days?",
        "answer": "Employees receive 20 days.",
        "reference_answer": "20 days",
        "context": ["Employees receive 20 days of annual leave."],
        "ratings": {
            "correctness": 5,
            "groundedness": 4,
            "citation_support": 4,
            "relevance": 5,
        },
        "hallucination": False,
    }
    review.update(overrides)
    return review


def test_validate_review_accepts_complete_review():
    review = validate_review(make_review(), 1)

    assert review["case_id"] == "case-1"
    assert review["ratings"]["correctness"] == 5
    assert review["hallucination"] is False


@pytest.mark.parametrize("value", [True, 0, 6, 4.0, "5"])
def test_validate_review_rejects_non_integer_or_out_of_range_ratings(value):
    review = make_review()
    review["ratings"]["correctness"] = value

    with pytest.raises(ValueError, match="integer from 1 to 5"):
        validate_review(review, 1)


def test_validate_review_rejects_missing_rating_dimension():
    review = make_review()
    del review["ratings"]["relevance"]

    with pytest.raises(ValueError, match="ratings must contain exactly"):
        validate_review(review, 1)


def test_validate_review_requires_boolean_hallucination_flag():
    with pytest.raises(ValueError, match="hallucination must be a boolean"):
        validate_review(make_review(hallucination=0), 1)


def test_load_reviews_rejects_duplicate_case_reviewer_pair(tmp_path):
    path = tmp_path / "reviews.jsonl"
    line = json.dumps(make_review())
    path.write_text(line + "\n" + line + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate review"):
        load_reviews(path)


def test_load_reviews_rejects_invalid_json_with_line_number(tmp_path):
    path = tmp_path / "reviews.jsonl"
    path.write_text("{not-json}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="line 1: invalid JSON"):
        load_reviews(path)


def test_summarize_reviews_reports_metrics_and_case_disagreement():
    first = validate_review(make_review(), 1)
    second = validate_review(
        make_review(
            reviewer_id="reviewer-2",
            ratings={
                "correctness": 3,
                "groundedness": 4,
                "citation_support": 2,
                "relevance": 5,
            },
            hallucination=True,
        ),
        2,
    )

    summary = summarize_reviews([first, second])

    assert summary["review_count"] == 2
    assert summary["case_count"] == 1
    assert summary["reviewer_count"] == 2
    assert summary["ratings"]["correctness"]["mean"] == 4.0
    assert summary["ratings"]["correctness"]["positive_rate_4_or_5"] == 0.5
    assert summary["ratings"]["citation_support"]["low_rate_1_or_2"] == 0.5
    assert summary["hallucination"]["count"] == 1
    assert summary["hallucination"]["rate"] == 0.5
    assert summary["reviewer_disagreement"]["correctness"]["mean_rating_range"] == 2


def test_summarize_reviews_rejects_empty_input():
    with pytest.raises(ValueError, match="reviews must be non-empty"):
        summarize_reviews([])
