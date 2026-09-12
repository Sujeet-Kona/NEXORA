import pytest

from backend.services.embedding_service import EmbeddingService


class FakeEmbeddings:
    def embed_documents(self, texts):
        return [
            [float(index), 1.0]
            for index, _ in enumerate(texts)
        ]

    def embed_query(self, text):
        return [1.0, 2.0]


def make_service():
    service = object.__new__(EmbeddingService)
    service.model_name = "fake"
    service._embeddings = FakeEmbeddings()
    return service


def test_embed_documents():
    service = make_service()

    result = service.embed_documents(
        ["first", "second"]
    )

    assert result == [
        [0.0, 1.0],
        [1.0, 1.0],
    ]


def test_embed_query():
    service = make_service()

    result = service.embed_query(
        "What is the leave policy?"
    )

    assert result == [1.0, 2.0]


def test_empty_documents():
    service = make_service()

    assert service.embed_documents([]) == []


def test_empty_query_rejected():
    service = make_service()

    with pytest.raises(ValueError):
        service.embed_query("   ")
