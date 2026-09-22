import pytest

from qdrant_client import QdrantClient, models

from backend.core.config import settings
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

    repository.upsert_chunk(
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

    repository.upsert_chunk(
        chunk_id=1,
        vector=vector,
        organization_id=10,
        document_id=100,
        chunk_index=0,
    )

    repository.delete_chunk(
        1,
        organization_id=10,
    )

    assert len(calls) == 1


def test_upsert_and_search(repository):
    vector_a = [1.0] + [0.0] * 1023
    vector_b = [0.0, 1.0] + [0.0] * 1022

    repository.upsert_chunk(
        chunk_id=1,
        vector=vector_a,
        organization_id=10,
        document_id=100,
        chunk_index=0,
    )

    repository.upsert_chunk(
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

    repository.upsert_chunk(
        chunk_id=1,
        vector=vector,
        organization_id=10,
        document_id=100,
        chunk_index=0,
    )

    repository.upsert_chunk(
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
        repository.upsert_chunk(
            chunk_id=1,
            vector=[1.0, 2.0],
            organization_id=10,
            document_id=100,
            chunk_index=0,
        )


def test_delete_chunk(repository):
    vector = [1.0] + [0.0] * 1023

    repository.upsert_chunk(
        chunk_id=1,
        vector=vector,
        organization_id=10,
        document_id=100,
        chunk_index=0,
    )

    repository.delete_chunk(
        1,
        organization_id=10,
    )

    result = repository.search(
        query_vector=vector,
        organization_id=10,
        limit=10,
    )

    assert result.points == []


def test_delete_chunk_is_tenant_scoped(repository):
    vector = [1.0] + [0.0] * 1023

    repository.upsert_chunk(
        chunk_id=1,
        vector=vector,
        organization_id=10,
        document_id=100,
        chunk_index=0,
    )

    repository.delete_chunk(
        1,
        organization_id=20,
    )

    result = repository.search(
        query_vector=vector,
        organization_id=10,
        limit=10,
    )

    assert {
        point.id
        for point in result.points
    } == {1}


def test_delete_document_chunks_is_tenant_scoped(repository):
    vector = [1.0] + [0.0] * 1023

    repository.upsert_chunk(
        chunk_id=1,
        vector=vector,
        organization_id=10,
        document_id=100,
        chunk_index=0,
    )

    repository.upsert_chunk(
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

    repository.upsert_chunk(
        chunk_id=1,
        vector=vector,
        organization_id=10,
        document_id=100,
        chunk_index=0,
    )

    repository.upsert_chunk(
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

    repository.upsert_chunk(
        chunk_id=1,
        vector=vector,
        organization_id=10,
        document_id=100,
        chunk_index=0,
    )

    repository.upsert_chunk(
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
