import pytest

from backend.core.config import settings
from backend.repositories.qdrant_repository import (
    QdrantRepository,
)
from backend.services.embedding_service import (
    EmbeddingService,
)


@pytest.fixture
def real_qdrant():
    repository = QdrantRepository(
        is_local=False,
    )

    try:
        repository.client.get_collections()
    except Exception as exc:
        pytest.fail(
            f"Real Qdrant is not available: {exc}"
        )

    repository.ensure_collection()

    return repository


def test_real_qdrant_upsert_search_and_delete(
    real_qdrant,
):
    embedding_service = EmbeddingService()

    text = "Employees receive 20 days of annual leave."

    vector = embedding_service.embed_documents(
        [text]
    )[0]

    chunk_id = 910001
    organization_id = 910
    document_id = 9100

    real_qdrant.upsert_chunk(
        chunk_id=chunk_id,
        vector=vector,
        organization_id=organization_id,
        document_id=document_id,
        chunk_index=0,
    )

    result = real_qdrant.search(
        query_vector=vector,
        organization_id=organization_id,
        limit=5,
    )

    assert any(
        point.id == chunk_id
        for point in result.points
    )

    try:
        wrong_tenant_result = real_qdrant.search(
            query_vector=vector,
            organization_id=organization_id + 1,
            limit=5,
        )

        assert all(
            point.id != chunk_id
            for point in wrong_tenant_result.points
        )
    finally:
        real_qdrant.delete_chunk(chunk_id)

    deleted_result = real_qdrant.search(
        query_vector=vector,
        organization_id=organization_id,
        limit=5,
    )

    assert all(
        point.id != chunk_id
        for point in deleted_result.points
    )


def test_real_qdrant_collection_has_expected_dimension(
    real_qdrant,
):
    info = real_qdrant.client.get_collection(
        settings.qdrant_collection
    )

    vector_config = info.config.params.vectors

    if isinstance(vector_config, dict):
        size = next(
            iter(vector_config.values())
        ).size
    else:
        size = vector_config.size

    assert size == settings.embedding_dimension
