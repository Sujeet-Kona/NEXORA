from backend.db.models import User
from backend.repositories.document_chunk_repository import (
    create_document_chunk,
)
from backend.repositories.document_repository import (
    create_document,
)
from backend.services import bm25_service
from backend.services.hybrid_retrieval_service import (
    _bm25_search,
    _rrf_fuse,
)
from backend.services.organization_service import (
    create_organization_service,
)
from backend.services.retrieval_service import RetrievedChunk


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
        dense=dense,
        lexical=lexical,
    )

    assert results[0].chunk.chunk_id == 2


def test_bm25_search_attaches_page_provenance_and_document_name(
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

    results = _bm25_search(
        db=db,
        organization_id=organization.id,
        query="annual leave",
        limit=5,
    )

    bm25_service._cache.clear()

    assert len(results) == 1
    assert results[0].chunk_id == chunk.id
    assert results[0].document_name == "leave-policy.pdf"
    assert results[0].page_start == 2
    assert results[0].page_end == 4

