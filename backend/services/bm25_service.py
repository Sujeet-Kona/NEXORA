import re
from threading import RLock

from rank_bm25 import BM25Okapi
from sqlalchemy.orm import Session

from backend.db.models import DocumentChunk

_WORD_PATTERN = re.compile(r"\w+")


class BM25Index:
    def __init__(
        self,
        chunks: list[DocumentChunk],
    ):
        self.chunks = list(chunks)

        corpus = [
            self._tokenize(chunk.text)
            for chunk in self.chunks
        ]

        self.corpus_tokens = corpus
        self.bm25 = (
            BM25Okapi(corpus) if corpus else None
        )

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return _WORD_PATTERN.findall(
            text.lower(),
        )

    def search(
        self,
        query: str,
        limit: int,
        document_ids: list[int] | None = None,
    ) -> list[tuple[DocumentChunk, float]]:
        if self.bm25 is None:
            return []

        query_tokens = self._tokenize(query)

        if not query_tokens:
            return []

        scores = self.bm25.get_scores(query_tokens)

        query_terms = set(query_tokens)

        ranked = sorted(
            (
                (chunk, float(score))
                for chunk, score, tokens in zip(
                    self.chunks,
                    scores,
                    self.corpus_tokens,
                )
                if query_terms.intersection(tokens)
            ),
            key=lambda item: item[1],
            reverse=True,
        )

        if document_ids is not None:
            allowed = set(document_ids)

            ranked = [
                item
                for item in ranked
                if item[0].document_id in allowed
            ]

        return ranked[:limit]


_cache: dict[int, BM25Index] = {}
_lock = RLock()


def invalidate_bm25_index(
    organization_id: int,
) -> None:
    with _lock:
        _cache.pop(organization_id, None)


def get_bm25_index(
    db: Session,
    organization_id: int,
) -> BM25Index:
    with _lock:
        index = _cache.get(organization_id)

        if index is not None:
            return index

        chunks = (
            db.query(DocumentChunk)
            .filter(
                DocumentChunk.organization_id == organization_id,
            )
            .order_by(
                DocumentChunk.document_id,
                DocumentChunk.chunk_index,
            )
            .all()
        )

        index = BM25Index(chunks)
        _cache[organization_id] = index

        return index
