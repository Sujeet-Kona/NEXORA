import logging

import pytest

from backend.services.document_chunking import (
    split_document,
    split_text,
)
from backend.services.document_extraction import (
    ExtractedDocument,
    ExtractedPage,
)


def test_split_text_returns_multiple_chunks():
    text = (
        "Paragraph one. " * 150
        + "\n\n"
        + "Paragraph two. " * 150
    )

    chunks = split_text(
        text,
        chunk_size=300,
        chunk_overlap=50,
    )

    assert len(chunks) > 1
    assert all(chunk.strip() for chunk in chunks)


def test_split_text_preserves_content():
    text = (
        "Nexora policy section one.\n\n"
        "Nexora policy section two.\n\n"
        "Nexora policy section three."
    )

    chunks = split_text(
        text,
        chunk_size=100,
        chunk_overlap=20,
    )

    combined = "\n".join(chunks)

    assert "section one" in combined
    assert "section two" in combined
    assert "section three" in combined


def test_empty_text_returns_empty_list():
    assert split_text("   ") == []


def test_invalid_overlap_is_rejected():
    with pytest.raises(ValueError):
        split_text(
            "Nexora",
            chunk_size=100,
            chunk_overlap=100,
        )


def test_zero_overlap_is_allowed():
    chunks = split_text(
        "Nexora " * 100,
        chunk_size=100,
        chunk_overlap=0,
    )

    assert len(chunks) > 1


def make_document(
    *page_texts: str,
) -> ExtractedDocument:
    return ExtractedDocument(
        pages=tuple(
            ExtractedPage(
                page_number=number,
                text=text,
            )
            for number, text in enumerate(
                page_texts,
                start=1,
            )
        )
    )


def test_split_document_preserves_split_text_boundaries():
    document = make_document(
        "Nexora policy one. " * 200,
        "Nexora policy two. " * 200,
    )

    spans = split_document(document)

    assert [span.text for span in spans] == split_text(
        document.text
    )


def test_split_document_maps_chunks_inside_a_single_page():
    document = make_document(
        "Clause one applies. " * 60,
    )

    spans = split_document(
        document,
        chunk_size=300,
        chunk_overlap=50,
    )

    assert len(spans) > 1
    assert all(
        (span.page_start, span.page_end) == (1, 1)
        for span in spans
    )


def test_split_document_reports_a_span_across_pages():
    document = make_document(
        "Page one clause. " * 5,
        "Page two clause. " * 5,
        "Page three clause. " * 5,
    )

    spans = split_document(document)

    assert len(spans) == 1
    assert spans[0].page_start == 1
    assert spans[0].page_end == 3


def test_split_document_attributes_chunks_to_their_page():
    document = make_document(
        "Alpha section. " * 300,
        "Beta section. " * 300,
        "Gamma section. " * 300,
    )

    spans = split_document(document)

    assert len(spans) > 1

    spans_by_page = {
        (span.page_start, span.page_end)
        for span in spans
    }

    assert (1, 1) in spans_by_page
    assert (3, 3) in spans_by_page

    for span in spans:
        expected = "Alpha" if span.page_start == 1 else None

        if expected:
            assert expected in span.text


def test_split_document_ignores_stripped_leading_whitespace():
    document = make_document(
        "\n\n   \n\nClause one applies. " * 30,
    )

    assert document.text.startswith("Clause one")

    spans = split_document(
        document,
        chunk_size=300,
        chunk_overlap=50,
    )

    assert spans
    assert all(
        (span.page_start, span.page_end) == (1, 1)
        for span in spans
    )


def test_split_document_does_not_cite_an_blank_page():
    document = make_document(
        "   \n\n  ",
        "Clause two applies. " * 30,
    )

    spans = split_document(
        document,
        chunk_size=300,
        chunk_overlap=50,
    )

    assert spans
    assert all(
        span.page_start == 2
        for span in spans
    )


def test_split_document_returns_empty_for_blank_document():
    document = make_document("   ", "\n\n")

    assert split_document(document) == []


def test_split_document_rejects_invalid_overlap():
    document = make_document("Nexora clause.")

    with pytest.raises(ValueError):
        split_document(
            document,
            chunk_size=100,
            chunk_overlap=100,
        )


def test_split_document_without_page_mapping_warns(
    monkeypatch,
    caplog,
):
    document = make_document("Clause one applies.")

    monkeypatch.setattr(
        "backend.services.document_chunking.split_text",
        lambda *args, **kwargs: ["reflowed text"],
    )

    caplog.set_level(
        logging.WARNING,
        logger="backend.services.document_chunking",
    )

    spans = split_document(document)

    assert len(spans) == 1
    assert spans[0].text == "reflowed text"
    assert spans[0].page_start is None
    assert spans[0].page_end is None
    assert "Could not map 1 of 1 chunks" in caplog.text


def test_split_text_structural_heading_boundary():
    """Text with a heading line must not glue the heading onto the prior
    section when the two are separated by only a single newline."""
    text = (
        "Intro paragraph with some filler content.\n"
        "# Heading Section\n"
        "Body content under the heading goes here."
    )

    chunks = split_text(text, chunk_size=120, chunk_overlap=0)

    # The heading must start its own chunk rather than being glued on
    # to the intro paragraph. "# Heading Section" is short enough that
    # it would fit with the intro if boundaries were not respected.
    heading_chunks = [
        c for c in chunks if c.startswith("# Heading Section")
    ]

    assert heading_chunks, (
        "Expected at least one chunk starting with the heading, "
        f"got: {chunks}"
    )


def test_split_text_filters_empty_chunks():
    """If structural processing or the splitter emit whitespace-only
    fragments they must not appear in the final result."""
    text = (
        "Proper body text. " * 20
        + "\n\n  \n\n  \n\n"
        + "More proper body text. " * 20
    )

    chunks = split_text(text, chunk_size=100, chunk_overlap=0)

    assert chunks
    assert all(c.strip() for c in chunks), (
        f"No chunk should be empty or whitespace-only, got: {chunks}"
    )


def test_split_text_collapses_consecutive_duplicates():
    """A duplicated chunk at a page boundary must be deduplicated."""
    # Construct a short text that, combined with overlap, produces a
    # duplicated tail then tail-then-head chunk.
    sentence = "Repeat the same boundary sentence."
    # With chunk_size ~half the sentence and overlap matching the tail,
    # consecutive duplicate collapses cover the edge case the splitter
    # would otherwise emit twice.
    text = (sentence + " ") * 2 + sentence

    chunks = split_text(text, chunk_size=len(sentence) + 1, chunk_overlap=0)

    for i in range(len(chunks) - 1):
        assert chunks[i] != chunks[i + 1], (
            f"Consecutive duplicate chunks must be collapsed: "
            f"chunk[{i}] == chunk[{i+1}]"
        )


def test_chunk_size_configurable():
    """chunk_size and chunk_overlap parameters must be respected: every
    output chunk must be <= chunk_size in length (after our stripping)."""
    long_text = "Line of policy content. " * 500

    for size, overlap in [(500, 50), (2000, 300)]:
        chunks = split_text(
            long_text,
            chunk_size=size,
            chunk_overlap=overlap,
        )
        assert chunks, f"Expected non-empty chunks for size={size}"
        for chunk in chunks:
            assert len(chunk) <= size, (
                f"Chunk len={len(chunk)} exceeds configured size={size}"
            )


def test_known_corpus_document_chunk_count_reasonable():
    """Using the real benchmark-data leave_policy.docx, ensure chunking
    produces a finite, sensible number of chunks. This guards against a
    regression where a separator bug explodes the chunk count."""
    from pathlib import Path
    from backend.evaluation.dataset import (
        BENCHMARK_DATA_DIR,
        DOCX_CONTENT_TYPE,
    )
    from backend.services.document_extraction import extract_document

    path = BENCHMARK_DATA_DIR / "leave_policy.docx"
    if not path.is_file():
        pytest.skip("benchmark-data corpus not available")

    doc = extract_document(
        filename=path.name,
        content_type=DOCX_CONTENT_TYPE,
        content=path.read_bytes(),
    )

    spans = split_document(doc)

    assert 1 <= len(spans) <= 50, (
        f"leave_policy produced an unreasonable chunk count: {len(spans)}"
    )
    assert all(span.text.strip() for span in spans)
    # Every span must have metadata populated, not None everywhere.
    page_populated = sum(
        1 for s in spans if s.page_start is not None
    )
    assert page_populated >= len(spans) // 2, (
        "Majority of spans must have page provenance attached"
    )
