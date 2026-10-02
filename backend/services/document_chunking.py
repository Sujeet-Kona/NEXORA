import logging
import re
from dataclasses import dataclass

from langchain_text_splitters import RecursiveCharacterTextSplitter

from backend.core.logging import LOGGER_NAME
from backend.services.document_extraction import (
    ExtractedDocument,
)


logger = logging.getLogger(LOGGER_NAME)


DEFAULT_CHUNK_SIZE = 3000
DEFAULT_CHUNK_OVERLAP = 400

# Markdown-style heading lines emitted by the structural DOCX extractor.
# A match here should trigger a chunk boundary whenever possible.
_HEADING_LINE_RE = re.compile(
    r"^#{1,6} [^\n]*$",
    re.MULTILINE,
)

# Maximum number of consecutive duplicate empty/whitespace chunk tokens the
# filter will drop. Kept small so it never hides an actual bug.
_MAX_STRIP_PASSES = 3


@dataclass(frozen=True)
class ChunkSpan:
    text: str
    page_start: int | None
    page_end: int | None


def _ensure_structural_heading_boundaries(text: str) -> str:
    """Pad heading lines with a paragraph break before them when missing.

    The default RecursiveCharacterTextSplitter already prefers
    paragraph-break boundaries. Headings extracted from DOCX documents
    are emitted as ``"# Heading\n"`` followed immediately by body text on
    a single ``\n``. Without this pre-pass, heading+body would glue on
    to the previous section because the splitter only sees a single
    newline. Adding a ``\n\n`` makes the boundary explicit.
    """
    if not _HEADING_LINE_RE.search(text):
        return text

    # Ensure every heading (except possibly at the very start) has a
    # double-newline before it. Using a lambda substitution so we do not
    # accidentally double-pad already-separated headings.
    padded = re.sub(
        r"(?<!\n\n)\n(?=#{1,6} )",
        "\n\n",
        text,
    )

    return padded


def _clean_chunks(chunks: list[str]) -> list[str]:
    """Drop empty / whitespace-only chunks and collapse consecutive exact
    duplicates. Chunk order is preserved."""
    cleaned: list[str] = []
    for raw in chunks:
        chunk = raw.strip()
        if not chunk:
            continue
        if cleaned and cleaned[-1] == chunk:
            # Collapse duplicate-adjacent content produced by overlap at
            # a page boundary. Never collapse across more than one pass
            # so a genuine repetition is still preserved.
            logger.debug(
                "Collapsing consecutive duplicate chunk of len=%d",
                len(chunk),
            )
            continue
        cleaned.append(chunk)

    return cleaned


def split_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[str]:
    if not text.strip():
        return []

    if chunk_overlap >= chunk_size:
        raise ValueError(
            "chunk_overlap must be smaller than chunk_size"
        )

    prepared = _ensure_structural_heading_boundaries(text)

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=[
            "\n\n",
            "\n",
            ". ",
            " ",
            "",
        ],
    )

    sections = re.split(
        r"(?m)(?=^#{1,6} )",
        prepared,
    )
    raw_chunks = [
        chunk
        for section in sections
        if section.strip()
        for chunk in splitter.split_text(section)
    ]

    return _clean_chunks(raw_chunks)


def _flat_text(
    document: ExtractedDocument,
) -> tuple[str, int]:
    joined = "\n".join(
        page.text
        for page in document.pages
    )

    return joined.strip(), len(joined) - len(joined.lstrip())


def _page_ranges(
    document: ExtractedDocument,
) -> list[tuple[int, int, int]]:
    ranges = []
    position = 0

    for page in document.pages:
        ranges.append(
            (
                page.page_number,
                position,
                position + len(page.text),
            )
        )

        # Pages are joined with a single newline.
        position += len(page.text) + 1

    return ranges


def _page_number(
    ranges: list[tuple[int, int, int]],
    offset: int,
) -> int:
    for page_number, _, end in ranges:
        if offset < end:
            return page_number

    return ranges[-1][0]


def _chunk_offsets(
    texts: list[str],
    flat_text: str,
) -> list[tuple[int, int] | None]:
    offsets = []
    cursor = 0

    for text in texts:
        index = flat_text.find(text, cursor)

        if index < 0:
            offsets.append(None)
            continue

        offsets.append((index, index + len(text)))
        cursor = index

    return offsets


def split_document(
    document: ExtractedDocument,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[ChunkSpan]:
    texts = split_text(
        document.text,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

    if not texts:
        return []

    flat_text, leading_offset = _flat_text(document)
    offsets = _chunk_offsets(texts, flat_text)
    ranges = _page_ranges(document)

    unmapped = sum(
        1
        for offset in offsets
        if offset is None
    )

    if unmapped:
        logger.warning(
            "Could not map %d of %d chunks to pages; "
            "page provenance omitted for those chunks",
            unmapped,
            len(offsets),
        )

    spans = []

    for text, offset in zip(texts, offsets):
        if offset is None:
            spans.append(
                ChunkSpan(
                    text=text,
                    page_start=None,
                    page_end=None,
                )
            )
            continue

        start, end = offset

        spans.append(
            ChunkSpan(
                text=text,
                page_start=_page_number(
                    ranges,
                    leading_offset + start,
                ),
                page_end=_page_number(
                    ranges,
                    leading_offset + end - 1,
                ),
            )
        )

    return spans
