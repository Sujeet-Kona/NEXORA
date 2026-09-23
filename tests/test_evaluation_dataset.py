from collections import Counter

from backend.evaluation.dataset import (
    build_corpus_chunks,
    load_cases,
    validate_dataset,
)


def test_dataset_has_30_cases_across_10_documents():
    cases = load_cases()

    documents = Counter(case.document for case in cases)

    assert len(cases) == 30
    assert len(documents) == 10
    assert set(documents.values()) == {3}


def test_corpus_chunks_cover_all_case_documents():
    cases = load_cases()
    chunks = build_corpus_chunks()

    assert {
        chunk.document_name for chunk in chunks
    } == {case.document for case in cases}

    assert len({chunk.id for chunk in chunks}) == len(chunks)

    assert all(
        chunk.text.strip() for chunk in chunks
    )


def test_every_case_has_ground_truth():
    validate_dataset()
