"""Process-local BM25 lexical index.

**Limitation**: the index cache lives in the API process memory. Each
worker process maintains its own independent cache:

* Multiple Uvicorn workers each build an independent copy of the index,
  consuming O(workers × corpus size) memory.
* Organization cache invalidation (``invalidate_bm25_index``) only
  clears the cache entry in the process that processes the document
  update — sibling workers will serve stale results until their cached
  instance hits the LRU cap or they are restarted.
* Deployment with more than one API process therefore experiences
  temporarily inconsistent lexical retrieval. A shared external cache
  (Redis, or a dedicated BM25 sidecar) would eliminate the staleness
  but introduces operational complexity. For single-instance portfolio
  deployments the process-local design is sufficient and honestly
  documented above.
"""

import re
from threading import RLock
from collections import OrderedDict

from rank_bm25 import BM25Okapi
from sqlalchemy.orm import Session

from backend.db.models import DocumentChunk
from backend.repositories.document_chunk_repository import (
    get_chunks_for_organization,
)

_WORD_PATTERN = re.compile(r"\w+")

# Maximum number of per-organization BM25 indexes kept in memory.
_MAX_CACHED_INDEXES = 64



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
        # Pre-build chunk→index mapping so document_id filtering can
        # filter the sparse index position list BEFORE computing scores.
        self._chunk_index_by_id = {
            chunk.id: i for i, chunk in enumerate(self.chunks)
        }
        # Pre-build chunk index → document id for filtering.
        self._document_id_by_chunk_index = [
            chunk.document_id for chunk in self.chunks
        ]

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

        if document_ids is None:
            # Fast path: full corpus, no doc_id filter.
            candidates = (
                (chunk, float(score))
                for chunk, score, tokens in zip(
                    self.chunks,
                    scores,
                    self.corpus_tokens,
                )
                if query_terms.intersection(tokens)
            )
        else:
            allowed = set(document_ids)
            candidates = (
                (self.chunks[i], float(scores[i]))
                for i, doc_id in enumerate(
                    self._document_id_by_chunk_index
                )
                if doc_id in allowed
                and query_terms.intersection(self.corpus_tokens[i])
            )

        ranked = sorted(
            candidates,
            key=lambda item: item[1],
            reverse=True,
        )

        return ranked[:limit]


_cache: "OrderedDict[int, BM25Index]" = OrderedDict()
_lock = RLock()


def invalidate_bm25_index(
    organization_id: int,
) -> None:
    with _lock:
        _cache.pop(organization_id, None)


def _evict_locked_if_needed() -> None:
    """Evict the least-recently *inserted* cache entry over the LRU cap.

    ``OrderedDict`` keeps insertion order; ``get_bm25_index`` calls
    ``move_to_end`` on hit so the oldest stale entries stay at the
    front and are the first to be dropped.
    """
    while len(_cache) > _MAX_CACHED_INDEXES:
        _cache.popitem(last=False)


def get_bm25_index(
    db: Session,
    organization_id: int,
) -> BM25Index:
    with _lock:
        index = _cache.get(organization_id)

        if index is not None:
            # LRU touch — move to most-recently used end.
            _cache.move_to_end(organization_id)
            return index

        chunks = get_chunks_for_organization(
            db=db,
            organization_id=organization_id,
        )

        index = BM25Index(chunks)
        _cache[organization_id] = index
        _evict_locked_if_needed()

        return index
