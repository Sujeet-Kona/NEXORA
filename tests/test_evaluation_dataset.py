from collections import Counter

from backend.evaluation.dataset import (
    _normalize_match_text,
    build_corpus_chunks,
    load_cases,
    load_negative_cases,
    validate_dataset,
)


def test_pdf_text_normalization_joins_hyphenated_line_breaks():
    assert _normalize_match_text("foundation avail-\nable") == (
        "foundation available"
    )


def test_dataset_has_60_cases_across_16_documents():
    cases = load_cases()
    documents = Counter(case.document for case in cases)

    assert len(cases) == 60
    assert len(documents) == 16

    docx_counts = {
        name: count
        for name, count in documents.items()
        if name.endswith(".docx")
    }
    pdf_counts = {
        name: count
        for name, count in documents.items()
        if name.endswith(".pdf")
    }

    assert len(docx_counts) == 10
    assert set(docx_counts.values()) == {3}

    assert len(pdf_counts) == 6
    assert set(pdf_counts.values()) == {5}


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


def test_every_case_declares_expected_answer_facts():
    cases = load_cases()

    assert all(case.expected for case in cases)

    assert all(
        fact.strip()
        for case in cases
        for fact in case.expected
    )


def test_negative_case_topics_are_absent_from_corpus():
    negative_cases = load_negative_cases()

    assert len(negative_cases) == 6

    corpus_text = " ".join(
        chunk.text for chunk in build_corpus_chunks()
    ).lower()

    for case in negative_cases:
        assert case.topic.lower() not in corpus_text
