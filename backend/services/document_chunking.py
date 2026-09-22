import logging
from dataclasses import dataclass

from langchain_text_splitters import RecursiveCharacterTextSplitter

from backend.services.document_extraction import (
    ExtractedDocument,
)


logger = logging.getLogger(__name__)


DEFAULT_CHUNK_SIZE = 3000
DEFAULT_CHUNK_OVERLAP = 400


@dataclass(frozen=True)
class ChunkSpan:
    text: str
    page_start: int | None
    page_end: int | None


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

    return splitter.split_text(text)


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
