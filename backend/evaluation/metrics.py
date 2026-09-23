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
