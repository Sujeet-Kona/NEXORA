"""Run the expanded benchmark without weakening the canonical benchmark contract.

The canonical dataset remains stable for backwards-compatible historical
results. This runner adds the grounded expansion cases at runtime and then
reuses the same retrieval/answer benchmark implementations.

Examples:
    python -m backend.evaluation.expanded_benchmark
    python -m backend.evaluation.expanded_benchmark --live
"""

from backend.evaluation import dataset
from backend.evaluation.expanded_cases import (
    EXPANDED_CASE_DATA,
    EXPANDED_NEGATIVE_CASE_DATA,
)


dataset._CASE_DATA = [*dataset._CASE_DATA, *EXPANDED_CASE_DATA]
dataset._NEGATIVE_CASE_DATA = [
    *dataset._NEGATIVE_CASE_DATA,
    *EXPANDED_NEGATIVE_CASE_DATA,
]


def main() -> None:
    dataset.validate_dataset()

    import sys

    if "answer" in sys.argv[0].lower():
        raise RuntimeError("Use the retrieval benchmark entry point for this runner")

    from backend.evaluation.benchmark import main as benchmark_main

    benchmark_main()


if __name__ == "__main__":
    main()
