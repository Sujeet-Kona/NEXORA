from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any

import pymupdf
from docx import Document as DocxDocument
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml.ns import qn
from docx.table import Table as DocxTable
from docx.text.paragraph import Paragraph

from backend.core.exceptions import DocumentExtractionError


DOCX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)

# Minimum text density (characters per page) to consider a PDF page
# "text-bearing" rather than a probable scanned image page.
MIN_TEXT_CHARS_PER_PAGE = 60

# Fraction of pages that must have usable text before we consider
# the PDF sufficiently extracted (otherwise flag for OCR).
MIN_USABLE_PAGE_RATIO = 0.40

# DOCX style names used to detect document headings (case-insensitive).
DOCX_HEADING_STYLES = {
    "heading 1", "heading 2", "heading 3",
    "heading 4", "heading 5", "heading 6",
    "title", "subtitle",
}


@dataclass(frozen=True)
class ExtractedPage:
    page_number: int
    text: str
    # Estimated whether this page is mostly-images (i.e. needs OCR).
    image_only: bool = False


@dataclass(frozen=True)
class ExtractedDocument:
    pages: tuple[ExtractedPage, ...]
    # Free-form metadata extracted from the source document.
    metadata: dict[str, Any] = field(default_factory=dict)
    # Hint for downstream: whether normal extraction was poor and an
    # OCR pass (if available) should be preferred.
    recommends_ocr: bool = False
    # Pages where image-only detection triggered, in 1-based numbering.
    image_only_pages: tuple[int, ...] = field(default_factory=tuple)

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def text(self) -> str:
        return "\n".join(
            page.text
            for page in self.pages
        ).strip()

    @property
    def character_count(self) -> int:
        return len(self.text)

    @property
    def word_count(self) -> int:
        return len(self.text.split())


def _sanitize_extracted_text(text: str) -> str:
    """Remove characters that PostgreSQL TEXT cannot store."""
    return text.replace("\x00", "")


def _extract_pdf_page_content(
    page: pymupdf.Page,
    page_number: int,
) -> ExtractedPage:
    """Extract text from a single PDF page, including tables.

    Uses pymupdf native table detection (``find_tables``) so table cells
    are emitted in readable row order with a TAB separator rather than
    being silently shredded by the default ``get_text()`` layout
    algorithm. Returns a hint about whether the page looks scanned.
    """
    # 1) Extract standard text stream.
    base_text = _sanitize_extracted_text(
        page.get_text("text") or ""
    )

    # 2) Try to recover tables that were flattened / dropped by plain
    #    text extraction. Each cell is joined with its row.
    table_parts: list[str] = []
    try:
        page_tables = page.find_tables()
        for table in page_tables.tables:
            try:
                rows = table.extract()
            except Exception:
                continue

            if not rows:
                continue

            for row in rows:
                cells = [
                    (cell.strip() if isinstance(cell, str) else "")
                    for cell in row
                    if cell is not None
                ]
                joined = " | ".join(c for c in cells if c)
                if joined:
                    table_parts.append(joined)
    except Exception:
        # Table detection itself should never break extraction; fall
        # back to the text we already have.
        pass

    # Combine stream text with any recovered table rows. Deduplicate
    # across a separator so tables do not double-encode when the base
    # text already included them.
    combined = base_text
    if table_parts:
        tables_block = "\n".join(table_parts)
        # Only append if the recovered content is materially different
        # from what we already have; simple substring check is sufficient
        # here because pymupdf get_text() often drops tables entirely.
        if tables_block[:80] and tables_block[:80] not in base_text:
            combined = (combined.rstrip() + "\n" + tables_block).strip()

    clean_text = "\n".join(
        line.strip()
        for line in _sanitize_extracted_text(combined).splitlines()
        if line.strip()
    )

    # Heuristic: a page with fewer than MIN_TEXT_CHARS_PER_PAGE after
    # stripping whitespace is most likely a scanned image page.
    image_only = len(clean_text) < MIN_TEXT_CHARS_PER_PAGE

    return ExtractedPage(
        page_number=page_number,
        text=clean_text,
        image_only=image_only,
    )


def extract_pdf_document(
    content: bytes,
) -> ExtractedDocument:
    try:
        with pymupdf.open(
            stream=content,
            filetype="pdf",
        ) as pdf:
            # Pull document-level metadata (all are optional strings).
            raw_meta = pdf.metadata or {}
            metadata: dict[str, Any] = {}
            for key, value in raw_meta.items():
                if isinstance(value, str) and value.strip():
                    metadata[key.lower()] = value.strip()
            metadata["page_count_pdf"] = pdf.page_count
            metadata["is_encrypted"] = bool(pdf.is_encrypted)

            pages: list[ExtractedPage] = []
            for page_number, page in enumerate(pdf, start=1):
                pages.append(
                    _extract_pdf_page_content(page, page_number)
                )

        image_only_pages = tuple(
            page.page_number
            for page in pages
            if page.image_only
        )

        # Decide whether the extraction quality is poor enough that the
        # caller should fall back to OCR (if an OCR backend is
        # available). A single scanned page in a 100-page document is
        # not enough — we only recommend OCR when a material fraction
        # of pages looks image-only.
        if pages and image_only_pages:
            usable_ratio = (
                1.0 - (len(image_only_pages) / len(pages))
            )
            recommends_ocr = usable_ratio < MIN_USABLE_PAGE_RATIO
        else:
            recommends_ocr = False

        return ExtractedDocument(
            pages=tuple(pages),
            metadata=metadata,
            recommends_ocr=recommends_ocr,
            image_only_pages=image_only_pages,
        )

    except DocumentExtractionError:
        raise
    except Exception as exc:
        raise DocumentExtractionError(
            "Failed to extract PDF text"
        ) from exc


def _docx_is_heading(paragraph: Paragraph) -> str | None:
    """Return a heading prefix (e.g. "## ") if the paragraph is a heading.

    Checks the named style first; then falls back to the w:outlineLvl
    property if a style is not matched.
    """
    style_name = ""
    try:
        style_name = (paragraph.style.name or "").lower()
    except Exception:
        style_name = ""

    if style_name in DOCX_HEADING_STYLES:
        # Map Heading 1..6 → #..######; Title / Subtitle → #.
        if style_name.startswith("heading "):
            try:
                level = int(style_name.split()[-1])
            except ValueError:
                level = 1
            level = max(1, min(6, level))
            return "#" * level + " "
        return "# "

    # Outline-level fallback for custom heading styles.
    try:
        p_pr = paragraph._p.find(qn("w:pPr"))
        if p_pr is not None:
            outline = p_pr.find(qn("w:outlineLvl"))
            if outline is not None:
                val = outline.get(qn("w:val"))
                if val is not None:
                    try:
                        level = int(val) + 1  # outline 0 → H1
                        level = max(1, min(6, level))
                        return "#" * level + " "
                    except ValueError:
                        pass
    except Exception:
        pass

    return None


def _docx_format_table(table: DocxTable) -> list[str]:
    """Render a DOCX table as simple row lines with " | " cell separators.

    If the first row is detectable as column headers (e.g. bolded cells
    or a different background), we keep it as-is; the separator already
    keeps column boundaries visually readable.
    """
    rows_out: list[str] = []
    for row in table.rows:
        cells: list[str] = []
        for cell in row.cells:
            cell_text = " ".join(
                line.strip()
                for line in cell.text.splitlines()
                if line.strip()
            ).strip()
            cells.append(cell_text)

        if any(cells):
            rows_out.append(
                " | ".join(c for c in cells if c != "")
            )

    return rows_out


def extract_docx_document(
    content: bytes,
) -> ExtractedDocument:
    try:
        document = DocxDocument(
            BytesIO(content)
        )

        parts: list[str] = []

        paragraphs_by_element = {
            paragraph._p: paragraph
            for paragraph in document.paragraphs
        }

        tables_by_element = {
            table._tbl: table
            for table in document.tables
        }

        # Pull core-properties metadata when available.
        metadata: dict[str, Any] = {}
        try:
            core = document.core_properties
            for attr in (
                "title", "author", "subject", "keywords",
                "category", "comments",
            ):
                value = getattr(core, attr, None)
                if isinstance(value, str) and value.strip():
                    metadata[attr] = value.strip()
        except Exception:
            pass

        for element in document.element.body:
            if element in paragraphs_by_element:
                paragraph = paragraphs_by_element[element]
                raw_text = _sanitize_extracted_text(paragraph.text).strip()

                if not raw_text:
                    continue

                heading_prefix = _docx_is_heading(paragraph)
                if heading_prefix is not None:
                    parts.append(f"{heading_prefix}{raw_text}")
                else:
                    parts.append(raw_text)

            elif element in tables_by_element:
                table = tables_by_element[element]
                parts.extend(_docx_format_table(table))

        # DOCX has no fixed pagination, so the body is one logical page.
        page = ExtractedPage(
            page_number=1,
            text="\n".join(parts),
        )

        return ExtractedDocument(
            pages=(page,),
            metadata=metadata,
        )

    except DocumentExtractionError:
        raise
    except Exception as exc:
        raise DocumentExtractionError(
            "Failed to extract DOCX text"
        ) from exc


def extract_document(
    filename: str,
    content_type: str | None,
    content: bytes,
) -> ExtractedDocument:
    extension = Path(filename).suffix.lower()

    if (
        extension == ".pdf"
        or content_type == "application/pdf"
    ):
        return extract_pdf_document(content)

    if (
        extension == ".docx"
        or content_type == DOCX_CONTENT_TYPE
    ):
        return extract_docx_document(content)

    raise DocumentExtractionError(
        "Unsupported document format"
    )
