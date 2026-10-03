import math
import re
import statistics


def recall_at_k(
    relevant: set[int],
    retrieved: list[int],
    k: int,
) -> float:
    if k < 1:
        raise ValueError("k must be at least 1")

    if not relevant:
        raise ValueError("relevant must be non-empty")

    top_k = set(retrieved[:k])

    return len(top_k & relevant) / len(relevant)


def precision_at_k(
    relevant: set[int],
    retrieved: list[int],
    k: int,
) -> float:
    if k < 1:
        raise ValueError("k must be at least 1")

    top_k = set(retrieved[:k])

    return len(top_k & relevant) / k


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
    """Mean-average-precision-style single-query AP@K.

    Sums precision@i for each position i where a relevant document is
    retrieved, divided by the TOTAL relevant count (not by the number
    retrieved). This is the canonical AP score used in BEIR benchmarks.
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


def normalize_answer_text(text: str) -> str:
    return " ".join(text.lower().split())


def fact_matches(
    answer: str,
    expected: tuple[str, ...] | list[str],
) -> bool:
    if not expected:
        raise ValueError("expected must be non-empty")

    normalized_answer = normalize_answer_text(answer)

    return any(
        normalize_answer_text(fact) in normalized_answer
        for fact in expected
    )


def indicates_refusal(
    answer: str,
    markers: tuple[str, ...] | list[str],
) -> bool:
    if not markers:
        raise ValueError("markers must be non-empty")

    normalized_answer = normalize_answer_text(answer)

    return any(
        normalize_answer_text(marker) in normalized_answer
        for marker in markers
    )


def latency_summary(values: list[float]) -> dict[str, float]:
    if not values:
        raise ValueError("values must be non-empty")

    ordered = sorted(values)

    rank = math.ceil(0.95 * len(ordered))
    p95_index = min(max(rank - 1, 0), len(ordered) - 1)

    return {
        "mean": statistics.fmean(ordered),
        "median": statistics.median(ordered),
        "p95": ordered[p95_index],
        "min": ordered[0],
        "max": ordered[-1],
    }


_CITATION_INDEX = re.compile(r"\[(\d{1,2})\]")


def citation_indices(answer: str) -> list[int]:
    """Return unique inline citation indices in first-seen order."""
    seen: set[int] = set()
    indices: list[int] = []

    for match in _CITATION_INDEX.finditer(answer):
        index = int(match.group(1))
        if index not in seen:
            seen.add(index)
            indices.append(index)

    return indices


def citations_are_valid_and_grounded(
    answer: str,
    sources,
    relevant_chunk_ids: set[int],
) -> bool:
    """Require an inline citation that maps to a retrieved relevant chunk."""
    indices = citation_indices(answer)

    if not indices:
        return False

    if any(index < 1 or index > len(sources) for index in indices):
        return False

    cited_chunk_ids = {
        sources[index - 1].chunk_id
        for index in indices
    }

    return bool(cited_chunk_ids & relevant_chunk_ids)
