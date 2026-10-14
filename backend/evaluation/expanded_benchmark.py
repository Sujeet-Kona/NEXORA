"""Run the expanded retrieval benchmark on the grounded expansion set."""

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
    from backend.evaluation.benchmark import main as benchmark_main
    benchmark_main()


if __name__ == "__main__":
    main()
