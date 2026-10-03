from io import BytesIO

import fitz
from docx import Document as DocxDocument
import pytest

from backend.core.exceptions import DocumentExtractionError
from backend.services.document_extraction import (
    _sanitize_extracted_text,
    extract_docx_document,
    extract_document,
    extract_pdf_document,
)


def make_pdf() -> bytes:
    document = fitz.open()

    page = document.new_page()

    page.insert_text(
        (72, 72),
        "Nexora HR Policy",
    )

    page.insert_text(
        (72, 100),
        "Employees receive 20 days of annual leave.",
    )

    content = document.tobytes()

    document.close()

    return content


def make_multi_page_pdf() -> bytes:
    document = fitz.open()

    first_page = document.new_page()

    first_page.insert_text(
        (72, 72),
        "First page content with enough searchable text to be classified as a text-bearing page.",
    )

    second_page = document.new_page()

    second_page.insert_text(
        (72, 72),
        "Second page content with enough searchable text to be classified as a text-bearing page.",
    )

    content = document.tobytes()

    document.close()

    return content


def make_image_only_pdf() -> bytes:
    document = fitz.open()

    page = document.new_page(
        width=200,
        height=200,
    )

    pixmap = fitz.Pixmap(
        fitz.csRGB,
        fitz.IRect(0, 0, 50, 50),
        False,
    )

    page.insert_image(
        fitz.Rect(0, 0, 200, 200),
        pixmap=pixmap,
    )

    content = document.tobytes()

    document.close()

    return content


def make_docx() -> bytes:
    document = DocxDocument()

    document.add_paragraph(
        "Nexora Security Policy"
    )

    document.add_paragraph(
        "All employees must use MFA."
    )

    table = document.add_table(
        rows=2,
        cols=2,
    )

    table.cell(0, 0).text = "Component"
    table.cell(0, 1).text = "Purpose"
    table.cell(1, 0).text = "MFA"
    table.cell(1, 1).text = "Account protection"

    buffer = BytesIO()

    document.save(buffer)

    return buffer.getvalue()


DOCX_TEXT = (
    "Nexora Security Policy\n"
    "All employees must use MFA.\n"
    "Component | Purpose\n"
    "MFA | Account protection"
)


def test_sanitize_extracted_text_removes_nul_bytes_preserves_unicode():
    text = "parameter \x00 value Φ ∆ Θ"

    sanitized = _sanitize_extracted_text(text)

    assert "\x00" not in sanitized
    assert sanitized == "parameter  value Φ ∆ Θ"


def test_extract_pdf_document_returns_numbered_pages():
    extracted = extract_pdf_document(
        make_pdf(),
    )

    assert extracted.page_count == 1
    assert len(extracted.pages) == 1
    assert extracted.pages[0].page_number == 1
    assert "Nexora HR Policy" in extracted.pages[0].text
    assert (
        "Employees receive 20 days of annual leave."
        in extracted.pages[0].text
    )


def test_extract_pdf_document_separates_page_text():
    extracted = extract_pdf_document(
        make_multi_page_pdf(),
    )

    assert extracted.page_count == 2

    assert [
        page.page_number
        for page in extracted.pages
    ] == [1, 2]

    assert "First page content" in extracted.pages[0].text
    assert "Second page content" not in extracted.pages[0].text

    assert "Second page content" in extracted.pages[1].text
    assert "First page content" not in extracted.pages[1].text


def test_flat_text_is_derived_from_pages():
    extracted = extract_pdf_document(
        make_multi_page_pdf(),
    )

    assert extracted.text == (
        "\n".join(
            page.text
            for page in extracted.pages
        ).strip()
    )

    assert not extracted.text.startswith("\n")
    assert not extracted.text.endswith("\n")


def test_pdf_stats_match_flat_text():
    extracted = extract_pdf_document(
        make_pdf(),
    )

    assert extracted.word_count == 10
    assert extracted.character_count == len(extracted.text)
    assert extracted.character_count == len(
        "Nexora HR Policy\n"
        "Employees receive 20 days of annual leave."
    )


def test_image_only_pdf_reports_zero_text_stats():
    extracted = extract_pdf_document(
        make_image_only_pdf(),
    )

    assert extracted.page_count == 1
    assert extracted.text == ""
    assert extracted.word_count == 0
    assert extracted.character_count == 0
    # A single entirely-empty page triggers image-only flagging and
    # therefore crosses the usable-text-ratio threshold that suggests
    # an OCR backend should be preferred.
    assert extracted.image_only_pages == (1,)
    assert extracted.pages[0].image_only is True
    assert extracted.recommends_ocr is True


def make_multi_page_mostly_image_pdf() -> bytes:
    """Three pages: first two image-only, third has text.

    Usable ratio = 1/3 ≈ 0.33 < 0.40 → recommends OCR.
    """
    document = fitz.open()

    # Two pure-image pages.
    for _ in range(2):
        page = document.new_page(width=200, height=200)
        pixmap = fitz.Pixmap(
            fitz.csRGB,
            fitz.IRect(0, 0, 20, 20),
            False,
        )
        page.insert_image(
            fitz.Rect(0, 0, 200, 200),
            pixmap=pixmap,
        )

    # One text-bearing page.
    text_page = document.new_page()
    text_page.insert_text(
        (72, 72),
        "Policy content here, with enough extracted text to classify this page as text-bearing.",
    )

    content = document.tobytes()
    document.close()
    return content


def test_mostly_image_pdf_recommends_ocr():
    extracted = extract_pdf_document(
        make_multi_page_mostly_image_pdf(),
    )

    assert extracted.page_count == 3
    assert extracted.image_only_pages == (1, 2)
    assert extracted.recommends_ocr is True
    # Third page still has usable text → overall stats are non-zero but
    # the OCR hint still fires because the majority of pages failed.
    assert extracted.character_count > 0


def test_text_only_pdf_does_not_recommend_ocr():
    """A normal text-only PDF must NOT trigger the OCR hint."""
    extracted = extract_pdf_document(
        make_multi_page_pdf(),
    )

    assert extracted.recommends_ocr is False
    assert extracted.image_only_pages == tuple()


def test_extracted_document_defaults_metadata_and_flags():
    """New dataclass fields have safe, well-typed defaults so callers that
    only get pages (e.g. old call sites) remain working."""
    extracted = extract_pdf_document(make_pdf())

    # Sane defaults
    assert isinstance(extracted.metadata, dict)
    assert isinstance(extracted.image_only_pages, tuple)
    assert isinstance(extracted.recommends_ocr, bool)
    # page_count_pdf key should always be populated because we set it
    # explicitly.
    assert "page_count_pdf" in extracted.metadata
    assert extracted.metadata["page_count_pdf"] == extracted.page_count
    # All pages must carry the image_only flag (bool, not None).
    assert all(
        isinstance(page.image_only, bool)
        for page in extracted.pages
    )


def test_extract_docx_document_is_one_logical_page():
    extracted = extract_docx_document(
        make_docx(),
    )

    assert extracted.page_count == 1
    assert extracted.pages[0].page_number == 1
    assert extracted.pages[0].text == DOCX_TEXT
    assert extracted.text == DOCX_TEXT
    assert extracted.word_count == 15
    assert extracted.character_count == len(DOCX_TEXT)


def test_extract_docx_document_includes_tables():
    extracted = extract_docx_document(
        make_docx(),
    )

    assert "Component" in extracted.text
    assert "Purpose" in extracted.text
    assert "MFA" in extracted.text
    assert "Account protection" in extracted.text


def test_extract_document_detects_pdf():
    extracted = extract_document(
        filename="policy.pdf",
        content_type="application/pdf",
        content=make_pdf(),
    )

    assert extracted.page_count == 1
    assert "Nexora HR Policy" in extracted.text


def test_extract_document_detects_docx():
    extracted = extract_document(
        filename="policy.docx",
        content_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        content=make_docx(),
    )

    assert extracted.page_count == 1
    assert "Nexora Security Policy" in extracted.text


def test_invalid_pdf_raises():
    with pytest.raises(DocumentExtractionError):
        extract_pdf_document(
            b"not a real pdf"
        )


def test_unsupported_format_raises():
    with pytest.raises(DocumentExtractionError):
        extract_document(
            filename="data.exe",
            content_type="application/octet-stream",
            content=b"bad",
        )


def make_docx_with_headings() -> bytes:
    """A DOCX using real heading styles so heading detection can be
    exercised."""
    document = DocxDocument()

    # Built-in styles for H1/H2.
    document.add_heading("Security Policy Overview", level=1)
    document.add_paragraph(
        "This document describes the company security policy."
    )
    document.add_heading("Authentication", level=2)
    document.add_paragraph("MFA is required for all accounts.")

    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def test_docx_heading_prefix_preserved():
    extracted = extract_docx_document(
        make_docx_with_headings(),
    )

    text = extracted.text

    # Heading 1 → "# " prefix.
    assert "# Security Policy Overview" in text
    # Heading 2 → "## " prefix.
    assert "## Authentication" in text
    # Non-heading paragraphs do NOT get a heading prefix.
    assert "MFA is required for all accounts." in text
    assert "# MFA" not in text  # guard against false positive prefixing


def test_docx_table_handles_multiline_cell_content():
    """Multi-line cells must be collapsed to single space-separated lines
    rather than introducing stray newlines that break row boundaries."""
    document = DocxDocument()
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "First line\nSecond line"
    table.cell(0, 1).text = "Simple"

    buffer = BytesIO()
    document.save(buffer)
    extracted = extract_docx_document(buffer.getvalue())

    row = extracted.pages[0].text
    # Cell joined without inner newlines.
    assert "First line Second line | Simple" in row


def test_docx_core_properties_collected():
    document = DocxDocument()
    try:
        document.core_properties.title = "Test Policy Title"
        document.core_properties.author = "Nexora HR"
    except Exception:
        pytest.skip("Core properties not writable in current env")

    document.add_paragraph("Body.")

    buffer = BytesIO()
    document.save(buffer)
    extracted = extract_docx_document(buffer.getvalue())

    assert extracted.metadata.get("title") == "Test Policy Title"
    assert extracted.metadata.get("author") == "Nexora HR"
