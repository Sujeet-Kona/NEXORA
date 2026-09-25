import pytest

from backend.core.exceptions import LLMGenerationError
from backend.db.database import SessionLocal
from backend.repositories.qdrant_repository import QdrantRepository
from backend.services.embedding_service import EmbeddingService
from backend.services.generation_service import NO_CONTEXT_ANSWER
from backend.services.llm.base import LLMClient
from backend.services.rag_service import (
    answer_question,
    stream_answer_question,
)
from backend.services.retrieval_service import RetrievedChunk


class FakeLLM:
    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        return "Employees receive 20 days of annual leave per year."


def make_chunk():
    return RetrievedChunk(
        chunk_id=101,
        document_id=7,
        organization_id=2,
        chunk_index=0,
        text=(
            "Employees receive 20 days of annual leave per year."
        ),
        score=0.91,
        page_start=2,
        page_end=2,
        document_name="leave_policy.pdf",
    )


def fake_retrieve(**kwargs):
    return [make_chunk()]


def test_answer_question_orchestrates_retrieval_and_generation():
    db = SessionLocal()

    try:
        result = answer_question(
            db=db,
            organization_id=2,
            question=(
                "How many annual leave days do employees receive?"
            ),
            embedding_service=EmbeddingService(),
            qdrant_repository=QdrantRepository(),
            llm_client=FakeLLM(),
            retrieve_fn=fake_retrieve,
        )

        assert (
            result.answer
            == "Employees receive 20 days of annual leave per year."
        )

        assert len(result.sources) == 1
        assert result.sources[0].chunk_id == 101

    finally:
        db.close()


def test_answer_question_forwards_document_ids():
    db = SessionLocal()

    captured = {}

    def capture_retrieve(**kwargs):
        captured.update(kwargs)
        return [make_chunk()]

    try:
        result = answer_question(
            db=db,
            organization_id=2,
            question=(
                "How many annual leave days do employees receive?"
            ),
            embedding_service=EmbeddingService(),
            qdrant_repository=QdrantRepository(),
            llm_client=FakeLLM(),
            retrieve_fn=capture_retrieve,
            document_ids=[42],
        )

        assert result.sources[0].chunk_id == 101

    finally:
        db.close()

    assert captured["document_ids"] == [42]
    assert captured["organization_id"] == 2


class FakeStreamLLM:
    def __init__(self, deltas=None, error=None):
        self.deltas = deltas or []
        self.error = error
        self.called = False

    def stream(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ):
        self.called = True

        if self.error is not None:
            raise self.error

        yield from self.deltas


def fake_retrieve(**kwargs):
    return [make_chunk()]


def empty_retrieve(**kwargs):
    return []


def collect_stream(**overrides):
    params = {
        "db": None,
        "organization_id": 2,
        "question": "How many annual leave days?",
        "embedding_service": None,
        "qdrant_repository": None,
        "llm_client": FakeStreamLLM(),
        "retrieve_fn": fake_retrieve,
    }
    params.update(overrides)

    return list(stream_answer_question(**params))


def test_stream_emits_tokens_then_done_with_timing():
    llm = FakeStreamLLM(
        deltas=[
            "Employees receive 20 days ",
            "of annual leave per year [1].",
        ]
    )

    events = collect_stream(llm_client=llm)

    assert [event["type"] for event in events] == [
        "token",
        "token",
        "done",
    ]

    assert events[0]["delta"] == "Employees receive 20 days "

    done = events[-1]

    assert done["answer"] == (
        "Employees receive 20 days of annual leave per year [1]."
    )
    assert done["sources"][0].chunk_id == 101
    assert done["timing"]["ttft_ms"] >= 0.0
    assert done["timing"]["total_ms"] >= (
        done["timing"]["ttft_ms"]
    )


def test_stream_final_answer_strips_out_of_range_markers():
    llm = FakeStreamLLM(
        deltas=["Leave is 20 days [1] and a bonus [3]."]
    )

    events = collect_stream(llm_client=llm)

    assert events[-1]["answer"] == (
        "Leave is 20 days [1] and a bonus."
    )


def test_stream_refuses_without_grounded_context():
    llm = FakeStreamLLM(deltas=["should not be used"])

    events = collect_stream(
        llm_client=llm,
        retrieve_fn=empty_retrieve,
    )

    assert [event["type"] for event in events] == [
        "token",
        "done",
    ]

    assert events[0]["delta"] == NO_CONTEXT_ANSWER
    assert events[-1]["answer"] == NO_CONTEXT_ANSWER
    assert events[-1]["sources"] == []
    assert llm.called is False


def test_stream_emits_error_event_when_llm_fails():
    llm = FakeStreamLLM(
        error=LLMGenerationError("Ollama exploded")
    )

    events = collect_stream(llm_client=llm)

    assert events[-1]["type"] == "error"
    assert events[-1]["detail"] == (
        "LLM provider request failed"
    )


def test_stream_emits_error_when_answer_is_blank():
    llm = FakeStreamLLM(deltas=["", "   "])

    events = collect_stream(llm_client=llm)

    assert events[-1]["type"] == "error"


def test_stream_validates_question_eagerly():
    with pytest.raises(
        ValueError,
        match="Question cannot be empty",
    ):
        stream_answer_question(
            db=None,
            organization_id=2,
            question="   ",
            embedding_service=None,
            qdrant_repository=None,
            llm_client=FakeStreamLLM(),
            retrieve_fn=fake_retrieve,
        )
