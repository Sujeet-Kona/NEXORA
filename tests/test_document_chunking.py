import pytest

from backend.services.document_chunking import split_text


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
