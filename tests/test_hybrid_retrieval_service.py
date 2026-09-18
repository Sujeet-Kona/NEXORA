from backend.services import bm25_service
from backend.services.hybrid_retrieval_service import _rrf_fuse
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

