import pytest

from qdrant_client import QdrantClient, models

from backend.core.config import settings
from backend.core.exceptions import VectorStoreError
from backend.repositories.qdrant_repository import (
    QdrantRepository,
)


@pytest.fixture()
def qdrant():
    return QdrantClient(":memory:")


@pytest.fixture()
def repository(qdrant):
    repository = QdrantRepository(
        client=qdrant,
        is_local=True,
    )

    repository.ensure_collection()

    return repository


def _seed(
    repository,
    *,
    chunk_id,
    vector,
    organization_id,
    document_id,
    chunk_index,
    document_version=1,
):
    repository.upsert_chunks(
        [
            (
                chunk_id,
                vector,
                organization_id,
                document_id,
                chunk_index,
                document_version,
            )
        ]
    )


def test_collection_is_created(repository, qdrant):
    collections = qdrant.get_collections()

    names = {
        collection.name
        for collection in collections.collections
    }

    assert settings.qdrant_collection in names


def test_collection_is_created_lazily_on_first_write(qdrant):
    repository = QdrantRepository(
        client=qdrant,
        is_local=True,
    )

    vector = [1.0] + [0.0] * 1023

    _seed(repository,
        chunk_id=1,
        vector=vector,
        organization_id=10,
        document_id=100,
        chunk_index=0,
    )

    names = {
        collection.name
        for collection in qdrant.get_collections().collections
    }

    assert settings.qdrant_collection in names

    result = repository.search(
        query_vector=vector,
        organization_id=10,
        limit=10,
    )

    assert {
        point.id
        for point in result.points
    } == {1}
    assert result.points[0].payload["version"] == 1


def test_ensure_collection_runs_once_per_repository(
    qdrant,
    monkeypatch,
):
    repository = QdrantRepository(
        client=qdrant,
        is_local=True,
    )

    calls = []
    original_get_collections = qdrant.get_collections

    def counting_get_collections():
        calls.append(1)
        return original_get_collections()

    monkeypatch.setattr(
        qdrant,
        "get_collections",
        counting_get_collections,
    )

    vector = [1.0] + [0.0] * 1023

    repository.ensure_collection()
    repository.ensure_collection()

    _seed(repository,
        chunk_id=1,
        vector=vector,
        organization_id=10,
        document_id=100,
        chunk_index=0,
    )

    repository.delete_document_chunks(
        document_id=100,
        organization_id=10,
    )

    assert len(calls) == 1


def test_upsert_and_search(repository):
    vector_a = [1.0] + [0.0] * 1023
    vector_b = [0.0, 1.0] + [0.0] * 1022

    _seed(repository,
        chunk_id=1,
        vector=vector_a,
        organization_id=10,
        document_id=100,
        chunk_index=0,
    )

    _seed(repository,
        chunk_id=2,
        vector=vector_b,
        organization_id=10,
        document_id=100,
        chunk_index=1,
    )

    result = repository.search(
        query_vector=vector_a,
        organization_id=10,
        limit=1,
    )

    assert len(result.points) == 1
    assert result.points[0].id == 1


def test_search_is_tenant_scoped(repository):
    vector = [1.0] + [0.0] * 1023

    _seed(repository,
        chunk_id=1,
        vector=vector,
        organization_id=10,
        document_id=100,
        chunk_index=0,
    )

    _seed(repository,
        chunk_id=2,
        vector=vector,
        organization_id=20,
        document_id=200,
        chunk_index=0,
    )

    result = repository.search(
        query_vector=vector,
        organization_id=10,
        limit=10,
    )

    ids = {
        point.id
        for point in result.points
    }

    assert ids == {1}


def test_wrong_embedding_dimension_is_rejected(repository):
    with pytest.raises(ValueError):
        _seed(repository,
            chunk_id=1,
            vector=[1.0, 2.0],
            organization_id=10,
            document_id=100,
            chunk_index=0,
        )


def test_delete_document_chunks_is_tenant_scoped(repository):
    vector = [1.0] + [0.0] * 1023

    _seed(repository,
        chunk_id=1,
        vector=vector,
        organization_id=10,
        document_id=100,
        chunk_index=0,
    )

    _seed(repository,
        chunk_id=2,
        vector=vector,
        organization_id=20,
        document_id=100,
        chunk_index=0,
    )

    repository.delete_document_chunks(
        document_id=100,
        organization_id=10,
    )

    result_a = repository.search(
        query_vector=vector,
        organization_id=10,
        limit=10,
    )

    result_b = repository.search(
        query_vector=vector,
        organization_id=20,
        limit=10,
    )

    assert result_a.points == []
    assert {
        point.id
        for point in result_b.points
    } == {2}


def test_search_filters_by_document_ids(repository):
    vector = [1.0] + [0.0] * 1023

    _seed(repository,
        chunk_id=1,
        vector=vector,
        organization_id=10,
        document_id=100,
        chunk_index=0,
    )

    _seed(repository,
        chunk_id=2,
        vector=vector,
        organization_id=10,
        document_id=200,
        chunk_index=0,
    )

    filtered = repository.search(
        query_vector=vector,
        organization_id=10,
        limit=10,
        document_ids=[100],
    )

    assert {
        point.id
        for point in filtered.points
    } == {1}

    foreign = repository.search(
        query_vector=vector,
        organization_id=10,
        limit=10,
        document_ids=[300],
    )

    assert foreign.points == []

    unfiltered = repository.search(
        query_vector=vector,
        organization_id=10,
        limit=10,
    )

    assert {
        point.id
        for point in unfiltered.points
    } == {1, 2}


def test_search_document_filter_stays_tenant_scoped(repository):
    vector = [1.0] + [0.0] * 1023

    _seed(repository,
        chunk_id=1,
        vector=vector,
        organization_id=10,
        document_id=100,
        chunk_index=0,
    )

    _seed(repository,
        chunk_id=2,
        vector=vector,
        organization_id=20,
        document_id=100,
        chunk_index=0,
    )

    result = repository.search(
        query_vector=vector,
        organization_id=10,
        limit=10,
        document_ids=[100],
    )

    assert {
        point.id
        for point in result.points
    } == {1}



def test_collection_initialization_errors_are_normalized(qdrant, monkeypatch):
    repository = QdrantRepository(
        client=qdrant,
        is_local=True,
    )

    def fail_to_list_collections():
        raise RuntimeError("raw Qdrant transport details")

    monkeypatch.setattr(
        qdrant,
        "get_collections",
        fail_to_list_collections,
    )

    with pytest.raises(
        VectorStoreError,
        match="Qdrant collection initialization failed",
    ) as exc_info:
        repository.ensure_collection()

    assert "raw Qdrant transport details" not in str(exc_info.value)
    assert repository._collection_ready is False


def test_generation_upsert_isolated_by_generation_and_search(repository):
    vector = [1.0] + [0.0] * 1023
    generation_a = "11111111-1111-4111-8111-111111111111"
    generation_b = "22222222-2222-4222-8222-222222222222"
    repository.upsert_generation_chunks(
        [
            (generation_a, vector, 10, 100, 0, 1),
            (generation_b, vector, 10, 100, 0, 1),
        ]
    )

    result_a = repository.search_generation(
        query_vector=vector,
        organization_id=10,
        generation_ids=[generation_a],
        limit=5,
    )
    result_b = repository.search_generation(
        query_vector=vector,
        organization_id=10,
        generation_ids=[generation_b],
        limit=5,
    )
    assert len(result_a.points) == 1
    assert len(result_b.points) == 1
    assert result_a.points[0].id != result_b.points[0].id
    assert result_a.points[0].payload["generation_id"] == generation_a
    assert result_b.points[0].payload["generation_id"] == generation_b


def test_generation_delete_only_removes_target_generation(repository):
    vector = [1.0] + [0.0] * 1023
    generation_a = "33333333-3333-4333-8333-333333333333"
    generation_b = "44444444-4444-4444-8444-444444444444"
    repository.upsert_generation_chunks(
        [
            (generation_a, vector, 11, 101, 0, 1),
            (generation_b, vector, 11, 101, 0, 1),
        ]
    )
    repository.delete_generation_chunks(
        generation_id=generation_a,
        document_id=101,
        organization_id=11,
    )
    remaining = repository.search_generation(
        query_vector=vector,
        organization_id=11,
        generation_ids=[generation_a, generation_b],
        limit=5,
    )
    assert len(remaining.points) == 1
    assert remaining.points[0].payload["generation_id"] == generation_b


def test_generation_search_is_tenant_scoped(repository):
    vector = [1.0] + [0.0] * 1023
    generation = "55555555-5555-4555-8555-555555555555"
    repository.upsert_generation_chunks(
        [(generation, vector, 12, 102, 0, 1)]
    )
    foreign = repository.search_generation(
        query_vector=vector,
        organization_id=99,
        generation_ids=[generation],
        limit=5,
    )
    assert foreign.points == []


def test_generation_upsert_rejects_invalid_uuid_and_vector_dimension(repository):
    vector = [1.0] + [0.0] * 1023
    with pytest.raises(ValueError, match="valid UUID"):
        repository.upsert_generation_chunks(
            [("not-a-uuid", vector, 1, 1, 0, 1)]
        )
    with pytest.raises(ValueError, match="Embedding dimension"):
        repository.upsert_generation_chunks(
            [("66666666-6666-4666-8666-666666666666", [1.0], 1, 1, 0, 1)]
        )


def test_generation_search_with_empty_generation_list_returns_empty(repository):
    result = repository.search_generation(
        query_vector=[1.0] + [0.0] * 1023,
        organization_id=1,
        generation_ids=[],
        limit=5,
    )
    assert result == []

def test_generation_point_count_is_scoped_to_generation_document_and_tenant(repository):
    vector = [1.0] + [0.0] * 1023
    target_generation = "66666666-6666-4666-8666-666666666666"
    other_generation = "77777777-7777-4777-8777-777777777777"
    repository.upsert_generation_chunks(
        [
            (target_generation, vector, 21, 201, 0, 1),
            (target_generation, vector, 21, 201, 1, 1),
            (other_generation, vector, 21, 201, 0, 1),
            (target_generation, vector, 21, 202, 0, 1),
            (target_generation, vector, 22, 201, 0, 1),
        ]
    )

    assert repository.count_generation_chunks(
        target_generation,
        document_id=201,
        organization_id=21,
    ) == 2
    assert repository.count_generation_chunks(
        target_generation,
        document_id=202,
        organization_id=21,
    ) == 1
    assert repository.count_generation_chunks(
        target_generation,
        document_id=201,
        organization_id=22,
    ) == 1
