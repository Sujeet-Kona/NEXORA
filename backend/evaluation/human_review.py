"""Aggregate explicit human judgments for NEXORA answer-quality reviews.

This module deliberately does not infer quality from lexical overlap. It
summarizes reviewer-entered ratings and reports the number of judgments behind
each metric. It does not calculate inter-rater reliability statistics.
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

RATING_FIELDS = (
    "correctness",
    "groundedness",
    "citation_support",
    "relevance",
)
REQUIRED_FIELDS = {
    "case_id",
    "reviewer_id",
    "question",
    "answer",
    "reference_answer",
    "context",
    "ratings",
    "hallucination",
}


def _non_empty_string(record: dict[str, Any], field: str, line_number: int) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"line {line_number}: {field} must be a non-empty string")
    return value.strip()


def validate_review(record: Any, line_number: int) -> dict[str, Any]:
    """Validate one human review record and return its normalized form."""
    if not isinstance(record, dict):
        raise ValueError(f"line {line_number}: each review must be a JSON object")

    missing = sorted(REQUIRED_FIELDS - record.keys())
    if missing:
        raise ValueError(f"line {line_number}: missing fields: {', '.join(missing)}")

    normalized = {
        field: _non_empty_string(record, field, line_number)
        for field in (
            "case_id",
            "reviewer_id",
            "question",
            "answer",
            "reference_answer",
        )
    }

    context = record["context"]
    if not isinstance(context, list) or any(
        not isinstance(item, str) or not item.strip() for item in context
    ):
        raise ValueError(
            f"line {line_number}: context must be a list of non-empty strings"
        )
    normalized["context"] = [item.strip() for item in context]

    ratings = record["ratings"]
    if not isinstance(ratings, dict) or set(ratings) != set(RATING_FIELDS):
        expected = ", ".join(RATING_FIELDS)
        raise ValueError(
            f"line {line_number}: ratings must contain exactly: {expected}"
        )

    clean_ratings = {}
    for field in RATING_FIELDS:
        value = ratings[field]
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 5:
            raise ValueError(
                f"line {line_number}: ratings.{field} must be an integer from 1 to 5"
            )
        clean_ratings[field] = value
    normalized["ratings"] = clean_ratings

    hallucination = record["hallucination"]
    if not isinstance(hallucination, bool):
        raise ValueError(f"line {line_number}: hallucination must be a boolean")
    normalized["hallucination"] = hallucination
    return normalized


def load_reviews(path: Path) -> list[dict[str, Any]]:
    """Load JSONL reviews and reject malformed or duplicate reviewer/case pairs."""
    reviews = []
    seen_pairs = set()
    with path.open(encoding="utf-8") as source:
        for line_number, raw_line in enumerate(source, start=1):
            if not raw_line.strip():
                continue
            try:
                record = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"line {line_number}: invalid JSON: {exc.msg}"
                ) from exc
            review = validate_review(record, line_number)
            pair = (review["case_id"], review["reviewer_id"])
            if pair in seen_pairs:
                raise ValueError(
                    f"line {line_number}: duplicate review for case_id={pair[0]!r} "
                    f"and reviewer_id={pair[1]!r}"
                )
            seen_pairs.add(pair)
            reviews.append(review)

    if not reviews:
        raise ValueError("review file contains no review records")
    return reviews


def summarize_reviews(reviews: list[dict[str, Any]]) -> dict[str, Any]:
    """Return transparent descriptive statistics over validated review records."""
    if not reviews:
        raise ValueError("reviews must be non-empty")

    values = {
        field: [review["ratings"][field] for review in reviews]
        for field in RATING_FIELDS
    }
    rating_summary = {}
    for field, scores in values.items():
        rating_summary[field] = {
            "mean": round(statistics.fmean(scores), 3),
            "positive_rate_4_or_5": round(
                sum(score >= 4 for score in scores) / len(scores), 4
            ),
            "low_rate_1_or_2": round(
                sum(score <= 2 for score in scores) / len(scores), 4
            ),
            "judgments": len(scores),
        }

    by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for review in reviews:
        by_case[review["case_id"]].append(review)

    disagreement = {}
    for field in RATING_FIELDS:
        ranges = [
            max(item["ratings"][field] for item in case_reviews)
            - min(item["ratings"][field] for item in case_reviews)
            for case_reviews in by_case.values()
            if len(case_reviews) > 1
        ]
        disagreement[field] = {
            "cases_with_multiple_reviewers": len(ranges),
            "mean_rating_range": round(statistics.fmean(ranges), 3) if ranges else None,
        }

    hallucination_count = sum(review["hallucination"] for review in reviews)
    return {
        "review_count": len(reviews),
        "case_count": len(by_case),
        "reviewer_count": len({review["reviewer_id"] for review in reviews}),
        "ratings": rating_summary,
        "hallucination": {
            "count": hallucination_count,
            "rate": round(hallucination_count / len(reviews), 4),
            "definition": (
                "reviewer marked the answer as containing an unsupported claim"
            ),
        },
        "reviewer_disagreement": disagreement,
        "limitations": [
            "These are descriptive human-review results for this reviewed sample only.",
            "No inter-rater reliability coefficient is calculated.",
            (
                "Ratings are not representative unless the sampling and reviewer "
                "protocol justify that claim."
            ),
            "Do not compare model versions unless the same cases and rubric are used.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Summarize human-reviewed NEXORA answer-quality JSONL."
    )
    parser.add_argument("input", type=Path, help="Path to the human review JSONL file")
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path for the JSON summary (prints to stdout when omitted)",
    )
    args = parser.parse_args()

    summary = summarize_reviews(load_reviews(args.input))
    rendered = json.dumps(summary, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
