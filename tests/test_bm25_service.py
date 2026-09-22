from backend.services import bm25_service


class FakeField:
    def __eq__(self, other):
        return True


class FakeDocumentChunkModel:
    organization_id = FakeField()
    document_id = FakeField()
    chunk_index = FakeField()


class FakeChunk:
    def __init__(
        self,
        chunk_id,
        document_id,
        chunk_index,
        text,
        organization_id=2,
    ):
        self.id = chunk_id
        self.document_id = document_id
        self.chunk_index = chunk_index
        self.text = text
        self.organization_id = organization_id


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *args):
        return self

    def order_by(self, *args):
        return self

    def all(self):
        return self.rows


class FakeDB:
    def __init__(self, rows):
        self.rows = rows

    def query(self, model):
        return FakeQuery(self.rows)


def test_bm25_index_is_cached_and_invalidated(monkeypatch):
    chunks = [
        FakeChunk(
            1,
            10,
            0,
            "annual leave policy",
        ),
        FakeChunk(
            2,
            10,
            1,
            "password security policy",
        ),
    ]

    db = FakeDB(chunks)

    monkeypatch.setattr(
        bm25_service,
        "DocumentChunk",
        FakeDocumentChunkModel,
    )

    bm25_service._cache.clear()

    first = bm25_service.get_bm25_index(
        db=db,
        organization_id=2,
    )

    second = bm25_service.get_bm25_index(
        db=db,
        organization_id=2,
    )

    assert first is second

    bm25_service.invalidate_bm25_index(2)

    third = bm25_service.get_bm25_index(
        db=db,
        organization_id=2,
    )

    assert third is not first


def test_bm25_empty_corpus_returns_no_results(
    monkeypatch,
):
    empty_index = bm25_service.BM25Index([])

    assert empty_index.search(
        query="annual leave",
        limit=5,
    ) == []

    monkeypatch.setattr(
        bm25_service,
        "DocumentChunk",
        FakeDocumentChunkModel,
    )

    bm25_service._cache.clear()

    try:
        index = bm25_service.get_bm25_index(
            db=FakeDB([]),
            organization_id=2,
        )

        assert index.search(
            query="annual leave",
            limit=5,
        ) == []

    finally:
        bm25_service._cache.clear()


def test_bm25_search_prefers_matching_chunk():
    chunks = [
        FakeChunk(
            1,
            10,
            0,
            "annual leave policy provides vacation days",
        ),
        FakeChunk(
            2,
            10,
            1,
            "password security requires strong credentials",
        ),
    ]

    db = FakeDB(chunks)

    monkeypatch = None
    bm25_service._cache.clear()

    fake_model = FakeDocumentChunkModel

    original_model = bm25_service.DocumentChunk
    bm25_service.DocumentChunk = fake_model

    try:
        index = bm25_service.get_bm25_index(
            db=db,
            organization_id=2,
        )

        results = index.search(
            query="annual leave",
            limit=1,
        )

        assert len(results) == 1
        assert results[0][0].id == 1

    finally:
        bm25_service.DocumentChunk = original_model
        bm25_service._cache.clear()


def test_bm25_search_filters_by_document_ids():
    chunks = [
        FakeChunk(
            1,
            10,
            0,
            "annual leave policy provides vacation days",
        ),
        FakeChunk(
            2,
            20,
            0,
            "annual leave rules for contractors",
        ),
    ]

    index = bm25_service.BM25Index(chunks)

    filtered = index.search(
        query="annual leave",
        limit=5,
        document_ids=[20],
    )

    assert [chunk.id for chunk, _ in filtered] == [2]

    missing = index.search(
        query="annual leave",
        limit=5,
        document_ids=[30],
    )

    assert missing == []

    unfiltered = index.search(
        query="annual leave",
        limit=5,
    )

    assert {
        chunk.id
        for chunk, _ in unfiltered
    } == {1, 2}


def test_bm25_document_filter_applies_before_limit():
    chunks = [
        FakeChunk(
            1,
            10,
            0,
            "annual leave policy vacation days",
        ),
        FakeChunk(
            2,
            10,
            1,
            "annual leave policy vacation days",
        ),
        FakeChunk(
            3,
            20,
            0,
            "annual leave policy",
        ),
    ]

    index = bm25_service.BM25Index(chunks)

    results = index.search(
        query="annual leave",
        limit=1,
        document_ids=[20],
    )

    assert len(results) == 1
    assert results[0][0].id == 3
