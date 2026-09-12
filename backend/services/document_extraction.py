from io import BytesIO
from pathlib import Path

import fitz
from docx import Document as DocxDocument

from backend.core.exceptions import DocumentExtractionError


def extract_pdf_text(content: bytes) -> str:
    try:
        with fitz.open(
            stream=content,
            filetype="pdf",
        ) as pdf:
            pages = []

            for page in pdf:
                pages.append(page.get_text())

        return "\n".join(pages).strip()

    except Exception as exc:
        raise DocumentExtractionError(
            "Failed to extract PDF text"
        ) from exc


def extract_docx_text(content: bytes) -> str:
    try:
        document = DocxDocument(
            BytesIO(content)
        )

        paragraphs = [
            paragraph.text
            for paragraph in document.paragraphs
            if paragraph.text.strip()
        ]

        return "\n".join(paragraphs).strip()

    except Exception as exc:
        raise DocumentExtractionError(
            "Failed to extract DOCX text"
        ) from exc


def extract_text(
    filename: str,
    content_type: str | None,
    content: bytes,
) -> str:
    extension = Path(filename).suffix.lower()

    if (
        extension == ".pdf"
        or content_type == "application/pdf"
    ):
        return extract_pdf_text(content)

    if (
        extension == ".docx"
        or content_type
        == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ):
        return extract_docx_text(content)

    raise DocumentExtractionError(
        "Unsupported document format"
    )
