import math
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
