import pytest

from backend.core.exceptions import LLMGenerationError
from backend.services.generation_service import NO_CONTEXT_ANSWER
from backend.services.llm.base import LLMUsage
from backend.services.rag_service import answer_question, stream_answer_question
from backend.services.retrieval_service import RetrievedChunk


class FakeLLM:
    last_usage = LLMUsage(input_tokens=100, output_tokens=20, total_tokens=120)

    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        return "Employees receive 20 days of annual leave per year."


def make_chunk():
    return RetrievedChunk(chunk_id=101, document_id=7, organization_id=2, chunk_index=0, text="Employees receive 20 days of annual leave per year.", score=0.91, page_start=2, page_end=2, document_name="leave_policy.pdf")


def fake_retrieve(**kwargs):
    return [make_chunk()]


def test_answer_question_orchestrates_retrieval_and_generation():
    result = answer_question(db=None, organization_id=2, question="How many annual leave days do employees receive?", embedding_service=None, qdrant_repository=None, llm_client=FakeLLM(), retrieve_fn=fake_retrieve)
    assert result.answer == "Employees receive 20 days of annual leave per year."
    assert len(result.sources) == 1
    assert result.sources[0].chunk_id == 101
    assert result.timing.retrieval_ms >= 0.0
    assert result.timing.generation_ms >= 0.0
    assert result.timing.total_ms >= result.timing.generation_ms
    assert result.usage == FakeLLM.last_usage


def test_answer_question_forwards_document_ids():
    captured = {}
    def capture_retrieve(**kwargs):
        captured.update(kwargs)
        return [make_chunk()]
    result = answer_question(db=None, organization_id=2, question="How many annual leave days do employees receive?", embedding_service=None, qdrant_repository=None, llm_client=FakeLLM(), retrieve_fn=capture_retrieve, document_ids=[42])
    assert result.sources[0].chunk_id == 101
    assert captured["document_ids"] == [42]
    assert captured["organization_id"] == 2


class FakeStreamLLM:
    def __init__(self, deltas=None, error=None, usage=None):
        self.deltas = deltas or []
        self.error = error
        self.called = False
        self.last_usage = usage

    def stream(self, *, system_prompt: str, user_prompt: str):
        self.called = True
        if self.error is not None:
            raise self.error
        yield from self.deltas


def empty_retrieve(**kwargs):
    return []


def collect_stream(**overrides):
    params = {"db": None, "organization_id": 2, "question": "How many annual leave days?", "embedding_service": None, "qdrant_repository": None, "llm_client": FakeStreamLLM(), "retrieve_fn": fake_retrieve}
    params.update(overrides)
    return list(stream_answer_question(**params))


def test_stream_emits_tokens_then_done_with_timing_and_usage():
    usage = LLMUsage(input_tokens=80, output_tokens=15, total_tokens=95)
    llm = FakeStreamLLM(deltas=["Employees receive 20 days ", "of annual leave per year [1]."], usage=usage)
    events = collect_stream(llm_client=llm)
    assert [event["type"] for event in events] == ["token", "token", "done"]
    done = events[-1]
    assert done["answer"] == "Employees receive 20 days of annual leave per year [1]."
    assert done["sources"][0].chunk_id == 101
    assert done["timing"]["retrieval_ms"] >= 0.0
    assert done["timing"]["generation_ms"] >= 0.0
    assert done["timing"]["ttft_ms"] >= 0.0
    assert done["timing"]["total_ms"] >= done["timing"]["ttft_ms"]
    assert done["usage"] == usage


def test_stream_final_answer_strips_out_of_range_markers():
    llm = FakeStreamLLM(deltas=["Leave is 20 days [1] and a bonus [3]."])
    events = collect_stream(llm_client=llm)
    assert events[-1]["answer"] == "Leave is 20 days [1] and a bonus."


def test_stream_refuses_without_grounded_context():
    llm = FakeStreamLLM(deltas=["should not be used"])
    events = collect_stream(llm_client=llm, retrieve_fn=empty_retrieve)
    assert [event["type"] for event in events] == ["token", "done"]
    assert events[0]["delta"] == NO_CONTEXT_ANSWER
    assert events[-1]["answer"] == NO_CONTEXT_ANSWER
    assert events[-1]["sources"] == []
    assert events[-1]["usage"] is None
    assert llm.called is False


def test_stream_emits_error_event_when_llm_fails():
    llm = FakeStreamLLM(error=LLMGenerationError("Ollama exploded"))
    events = collect_stream(llm_client=llm)
    assert events[-1]["type"] == "error"
    assert events[-1]["detail"] == "LLM provider request failed"


def test_stream_emits_error_when_answer_is_blank():
    llm = FakeStreamLLM(deltas=["", "   "])
    events = collect_stream(llm_client=llm)
    assert events[-1]["type"] == "error"


def test_stream_validates_question_eagerly():
    with pytest.raises(ValueError, match="Question cannot be empty"):
        stream_answer_question(db=None, organization_id=2, question="   ", embedding_service=None, qdrant_repository=None, llm_client=FakeStreamLLM(), retrieve_fn=fake_retrieve)


def test_stream_tokens_never_expose_out_of_range_markers():
    llm = FakeStreamLLM(deltas=["Leave is 20 days [1] and a bonus", " [", "3", "]."])
    events = collect_stream(llm_client=llm)
    streamed = "".join(event["delta"] for event in events if event["type"] == "token")
    assert "[3]" not in streamed
    assert "[1]" in streamed
    assert events[-1]["answer"] == "Leave is 20 days [1] and a bonus."
    assert streamed == events[-1]["answer"]

def test_default_rag_retrieval_merges_active_and_legacy_results(monkeypatch):
    import backend.services.rag_service as rag_service

    active = make_chunk()
    legacy = RetrievedChunk(chunk_id=202, document_id=8, organization_id=2, chunk_index=1, text="legacy text", score=0.87, page_start=3, page_end=3, document_name="legacy.pdf")
    calls = []
    monkeypatch.setattr(rag_service, "get_legacy_document_ids", lambda **kwargs: [8])

    def retrieve(**kwargs):
        calls.append(kwargs)
        return [active] if kwargs["use_active_generations"] else [legacy]


    monkeypatch.setattr(rag_service, "hybrid_retrieve_chunks", retrieve)
    result = answer_question(db=None, organization_id=2, question="policy", embedding_service=None, qdrant_repository=None, llm_client=FakeLLM(), retrieval_limit=5)
    assert {chunk.document_id for chunk in result.sources} == {7, 8}
    assert len(calls) == 2
    assert calls[1]["document_ids"] == [8]



def test_default_rag_retrieval_falls_back_to_legacy_only_documents(monkeypatch):
    import backend.services.rag_service as rag_service

    captured = []
    monkeypatch.setattr(rag_service, "get_legacy_document_ids", lambda **kwargs: [7, 8])

    def retrieve(**kwargs):
        captured.append(kwargs)
        return [make_chunk()] if kwargs["use_active_generations"] is False else []

    monkeypatch.setattr(rag_service, "hybrid_retrieve_chunks", retrieve)
    response = answer_question(
        db=None,
        organization_id=2,
        question="annual leave",
        embedding_service=None,
        qdrant_repository=None,
        llm_client=FakeLLM(),
    )
    assert response.sources
    assert captured[0]["use_active_generations"] is True
    assert captured[1]["use_active_generations"] is False
    assert captured[1]["document_ids"] == [7, 8]



def test_default_rag_retrieval_uses_active_generations(monkeypatch):
    import backend.services.rag_service as rag_service

    captured = []

    def active_retrieval(**kwargs):
        captured.append(kwargs)
        return [make_chunk()]

    monkeypatch.setattr(rag_service, "hybrid_retrieve_chunks", active_retrieval)
    monkeypatch.setattr(rag_service, "get_legacy_document_ids", lambda **kwargs: [])
    response = answer_question(
        db=None,
        organization_id=2,
        question="annual leave",
        embedding_service=None,
        qdrant_repository=None,
        llm_client=FakeLLM(),
    )
    assert response.sources
    assert captured[-1]["use_active_generations"] is True

    captured.clear()
    events = list(stream_answer_question(
        db=None,
        organization_id=2,
        question="annual leave",
        embedding_service=None,
        qdrant_repository=None,
        llm_client=FakeStreamLLM(deltas=["Leave is 20 days."]),
    ))
    assert events[-1]["type"] == "done"
    assert captured[-1]["use_active_generations"] is True
