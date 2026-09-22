from threading import RLock

from rank_bm25 import BM25Okapi
from sqlalchemy.orm import Session

from backend.db.models import DocumentChunk


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

        self.bm25 = (
            BM25Okapi(corpus) if corpus else None
        )

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return text.lower().split()

    def search(
        self,
        query: str,
        limit: int,
    ) -> list[tuple[DocumentChunk, float]]:
        if self.bm25 is None:
            return []

        scores = self.bm25.get_scores(
            self._tokenize(query)
        )

        ranked = sorted(
            zip(self.chunks, scores),
            key=lambda item: float(item[1]),
            reverse=True,
        )

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
