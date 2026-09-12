from io import BytesIO

import fitz
from docx import Document as DocxDocument
import pytest

from backend.core.exceptions import DocumentExtractionError
from backend.services.document_extraction import (
    extract_docx_text,
    extract_pdf_text,
    extract_text,
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


def make_docx() -> bytes:
    document = DocxDocument()

    document.add_paragraph(
        "Nexora Security Policy"
    )

    document.add_paragraph(
        "All employees must use MFA."
    )

    buffer = BytesIO()

    document.save(buffer)

    return buffer.getvalue()


def test_extract_pdf_text():
    content = make_pdf()

    text = extract_pdf_text(content)

    assert "Nexora HR Policy" in text
    assert (
        "Employees receive 20 days of annual leave."
        in text
    )


def test_extract_docx_text():
    content = make_docx()

    text = extract_docx_text(content)

    assert "Nexora Security Policy" in text
    assert "All employees must use MFA." in text


def test_extract_text_detects_pdf():
    content = make_pdf()

    text = extract_text(
        filename="policy.pdf",
        content_type="application/pdf",
        content=content,
    )

    assert "Nexora HR Policy" in text


def test_extract_text_detects_docx():
    content = make_docx()

    text = extract_text(
        filename="policy.docx",
        content_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        content=content,
    )

    assert "Nexora Security Policy" in text


def test_invalid_pdf_raises():
    with pytest.raises(DocumentExtractionError):
        extract_pdf_text(
            b"not a real pdf"
        )


def test_unsupported_format_raises():
    with pytest.raises(DocumentExtractionError):
        extract_text(
            filename="data.exe",
            content_type="application/octet-stream",
            content=b"bad",
        )
