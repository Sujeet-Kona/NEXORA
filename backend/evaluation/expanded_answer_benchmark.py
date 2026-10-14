"""Run the end-to-end answer benchmark on the expanded grounded dataset."""

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
    from backend.evaluation.answer_benchmark import main as answer_benchmark_main
    answer_benchmark_main()


if __name__ == "__main__":
    main()
