from io import BytesIO
from pathlib import Path

import pymupdf
from docx import Document as DocxDocument

from backend.core.exceptions import DocumentExtractionError


def extract_pdf_text(content: bytes) -> str:
    try:
        with pymupdf.open(
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

        parts = []

        paragraphs_by_element = {
            paragraph._p: paragraph
            for paragraph in document.paragraphs
        }

        tables_by_element = {
            table._tbl: table
            for table in document.tables
        }

        for element in document.element.body:
            if element in paragraphs_by_element:
                paragraph = paragraphs_by_element[element]

                if paragraph.text.strip():
                    parts.append(
                        paragraph.text.strip()
                    )

            elif element in tables_by_element:
                table = tables_by_element[element]

                for row in table.rows:
                    cells = [
                        cell.text.strip()
                        for cell in row.cells
                    ]

                    row_text = " | ".join(
                        cell
                        for cell in cells
                        if cell
                    )

                    if row_text:
                        parts.append(row_text)

        return "\n".join(parts).strip()

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
