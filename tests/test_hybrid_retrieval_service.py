from unittest.mock import Mock

import pytest

from backend.core.config import settings
from backend.db.models import User
from backend.repositories.document_chunk_repository import (
    create_document_chunk,
)
from backend.repositories.document_repository import (
    create_document,
)
from backend.services import bm25_service
from backend.services.hybrid_retrieval_service import (
    Reranker,
    _rrf_fuse,
    _sigmoid,
    hybrid_retrieve_chunks,
)
from backend.services.organization_service import (
    create_organization_service,
)
from backend.services.retrieval_service import RetrievedChunk
from backend.services.retrievers import LexicalRetriever


def make_chunk(
    chunk_id: int,
    text: str,
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id=1,
        organization_id=2,
        chunk_index=chunk_id,
        text=text,
        score=0.0,
        page_start=1,
        page_end=1,
        document_name="policy.pdf",
    )


def test_bm25_returns_matching_text():
    chunks = [
        make_chunk(1, "annual leave policy"),
        make_chunk(2, "password security policy"),
        make_chunk(3, "remote work policy"),
    ]

    index = bm25_service.BM25Index(
        chunks
    )

    results = index.search(
        query="annual leave",
        limit=2,
    )

    assert results
    assert results[0][0].chunk_id == 1


def test_rrf_fusion_promotes_documents_in_both_rankings():
    dense = [
        make_chunk(1, "dense first"),
        make_chunk(2, "shared result"),
    ]

    lexical = [
        make_chunk(3, "lexical first"),
        make_chunk(2, "shared result"),
    ]

    results = _rrf_fuse(
        [dense, lexical],
    )

    assert results[0].chunk.chunk_id == 2


def test_rrf_fusion_supports_more_than_two_rankings():
    shared = make_chunk(1, "shared result")

    results = _rrf_fuse(
        [
            [make_chunk(2, "first ranking"), shared],
            [make_chunk(3, "second ranking"), shared],
            [make_chunk(4, "third ranking"), shared],
        ],
    )

    assert results[0].chunk.chunk_id == 1


def test_lexical_retriever_attaches_page_provenance_and_document_name(
    db,
):
    bm25_service._cache.clear()

    owner = User(
        email="bm25-provenance@example.com",
        full_name="BM25 Provenance",
        password_hash="test-hash",
    )

    db.add(owner)
    db.commit()
    db.refresh(owner)

    organization = create_organization_service(
        db=db,
        name="BM25 Provenance Company",
        user_id=owner.id,
    )

    document = create_document(
        db=db,
        organization_id=organization.id,
        uploaded_by=owner.id,
        name="leave-policy.pdf",
    )

    chunk = create_document_chunk(
        db=db,
        document_id=document.id,
        organization_id=organization.id,
        chunk_index=0,
        text="annual leave policy details",
        page_start=2,
        page_end=4,
    )

    db.commit()
    db.refresh(chunk)

    results = LexicalRetriever(limit=5).retrieve(
        db=db,
        organization_id=organization.id,
        query="annual leave",
    )

    bm25_service._cache.clear()

    assert len(results) == 1
    assert results[0].chunk_id == chunk.id
    assert results[0].document_name == "leave-policy.pdf"
    assert results[0].page_start == 2
    assert results[0].page_end == 4


def test_hybrid_retrieve_chunks_applies_document_filter(
    db,
    monkeypatch,
):
    bm25_service._cache.clear()

    owner = User(
        email="hybrid-document-filter@example.com",
        full_name="Hybrid Document Filter",
        password_hash="test-hash",
    )

    db.add(owner)
    db.commit()
    db.refresh(owner)

    organization = create_organization_service(
        db=db,
        name="Hybrid Document Filter Company",
        user_id=owner.id,
    )

    document = create_document(
        db=db,
        organization_id=organization.id,
        uploaded_by=owner.id,
        name="leave-policy.pdf",
    )

    other_document = create_document(
        db=db,
        organization_id=organization.id,
        uploaded_by=owner.id,
        name="security-policy.pdf",
    )

    chunk = create_document_chunk(
        db=db,
        document_id=document.id,
        organization_id=organization.id,
        chunk_index=0,
        text="annual leave policy details",
    )

    other_chunk = create_document_chunk(
        db=db,
        document_id=other_document.id,
        organization_id=organization.id,
        chunk_index=0,
        text="annual leave accrued during probation",
    )

    db.commit()
    db.refresh(chunk)
    db.refresh(other_chunk)

    embedding = Mock()
    embedding.embed_query.return_value = (
        [1.0] * settings.embedding_dimension
    )

    qdrant = Mock()
    qdrant.search.return_value.points = [
        Mock(id=chunk.id, score=0.95),
        Mock(id=other_chunk.id, score=0.90),
    ]

    class StubReranker:
        def rerank(
            self,
            query,
            chunks,
        ):
            return chunks

    monkeypatch.setattr(
        "backend.services.hybrid_retrieval_service.get_reranker",
        lambda: StubReranker(),
    )

    results = hybrid_retrieve_chunks(
        db=db,
        organization_id=organization.id,
        query="annual leave policy",
        embedding_service=embedding,
        qdrant_repository=qdrant,
        document_ids=[other_document.id],
    )

    bm25_service._cache.clear()

    assert [
        result.document_id
        for result in results
    ] == [other_document.id]

    qdrant.search.assert_called_once_with(
        query_vector=[1.0] * settings.embedding_dimension,
        organization_id=organization.id,
        limit=settings.retrieval_dense_top_k,
        document_ids=[other_document.id],
    )


class StubRetriever:
    def __init__(self, chunks):
        self.chunks = chunks

    def retrieve(
        self,
        *,
        db,
        organization_id,
        query,
        document_ids=None,
    ):
        return self.chunks


def test_hybrid_retrieve_chunks_accepts_custom_retrievers(
    monkeypatch,
):
    shared = make_chunk(2, "shared result")

    first = StubRetriever(
        [
            make_chunk(1, "dense first"),
            shared,
        ],
    )

    second = StubRetriever(
        [
            make_chunk(3, "lexical first"),
            shared,
        ],
    )

    class StubReranker:
        def rerank(
            self,
            query,
            chunks,
        ):
            return chunks

    monkeypatch.setattr(
        "backend.services.hybrid_retrieval_service.get_reranker",
        lambda: StubReranker(),
    )

    results = hybrid_retrieve_chunks(
        db=None,
        organization_id=2,
        query="annual leave",
        embedding_service=None,
        qdrant_repository=None,
        retrievers=[first, second],
    )

    assert results[0].chunk_id == 2
    assert len(results) == settings.retrieval_top_k


def test_hybrid_retrieve_chunks_rejects_default_limits_with_custom_retrievers():
    retriever = StubRetriever([])

    with pytest.raises(ValueError):
        hybrid_retrieve_chunks(
            db=None,
            organization_id=2,
            query="annual leave",
            embedding_service=None,
            qdrant_repository=None,
            retrievers=[retriever],
            dense_limit=5,
        )


class FakeCrossEncoder:
    """Returns preset logits in pair order, like CrossEncoder.predict."""

    def __init__(self, logits):
        self.logits = list(logits)
        self.pairs = None

    def predict(self, pairs):
        self.pairs = pairs
        return self.logits


def make_reranker(logits):
    reranker = Reranker.__new__(Reranker)
    reranker.model = FakeCrossEncoder(logits)
    return reranker


def test_sigmoid_maps_logits_to_unit_interval():
    assert _sigmoid(0.0) == 0.5
    assert 0.0 < _sigmoid(-50.0) <= 1.0
    assert 0.0 < _sigmoid(50.0) <= 1.0
    assert _sigmoid(3.0) > 0.5
    assert _sigmoid(-3.0) < 0.5


def test_reranker_drops_chunks_below_relevance_threshold(monkeypatch):
    monkeypatch.setattr(settings, "retrieval_min_relevance", 0.5)

    relevant = make_chunk(1, "annual leave entitlement")
    irrelevant = make_chunk(2, "unrelated spreadsheet macros")

    reranker = make_reranker([3.0, -3.0])

    results = reranker.rerank(
        query="annual leave",
        chunks=[relevant, irrelevant],
    )

    assert [chunk.chunk_id for chunk in results] == [1]
    assert results[0].score == pytest.approx(_sigmoid(3.0))
    assert 0.0 <= results[0].score <= 1.0


def test_reranker_returns_empty_when_nothing_is_relevant(monkeypatch):
    monkeypatch.setattr(settings, "retrieval_min_relevance", 0.5)

    chunks = [
        make_chunk(1, "cryptocurrency investment policy"),
        make_chunk(2, "office parking arrangements"),
    ]

    reranker = make_reranker([-3.0, -4.0])

    results = reranker.rerank(
        query="how many annual leave days",
        chunks=chunks,
    )

    assert results == []


def test_reranker_orders_survivors_by_descending_relevance(monkeypatch):
    monkeypatch.setattr(settings, "retrieval_min_relevance", 0.5)

    chunks = [
        make_chunk(1, "weaker match"),
        make_chunk(2, "stronger match"),
    ]

    reranker = make_reranker([1.0, 4.0])

    results = reranker.rerank(
        query="annual leave",
        chunks=chunks,
    )

    assert [chunk.chunk_id for chunk in results] == [2, 1]
    assert results[0].score > results[1].score


def test_reranker_threshold_zero_keeps_everything(monkeypatch):
    monkeypatch.setattr(settings, "retrieval_min_relevance", 0.0)

    chunks = [
        make_chunk(1, "first"),
        make_chunk(2, "second"),
    ]

    reranker = make_reranker([-5.0, -6.0])

    results = reranker.rerank(
        query="annual leave",
        chunks=chunks,
    )

    assert len(results) == 2


def test_reranker_handles_empty_input():
    reranker = make_reranker([])

    assert reranker.rerank(query="annual leave", chunks=[]) == []


def test_min_relevance_default_is_within_unit_interval():
    assert 0.0 <= settings.retrieval_min_relevance <= 1.0


def test_min_relevance_setting_rejects_out_of_range_values():
    from pydantic import ValidationError

    from backend.core.config import Settings

    base = {
        "database_url": "sqlite://",
        "jwt_secret_key": "test-secret",
    }

    for bad_value in (-0.1, 1.1):
        with pytest.raises(ValidationError):
            Settings(
                retrieval_min_relevance=bad_value,
                **base,
            )
