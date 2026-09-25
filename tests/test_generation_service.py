import pytest

from backend.core.exceptions import LLMGenerationError
from backend.services.generation_service import generate_answer
from backend.services.retrieval_service import RetrievedChunk


class FakeLLM:
    def __init__(self):
        self.system_prompt = None
        self.user_prompt = None

    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt

        return (
            "Employees receive 20 days of annual leave per year."
        )


def make_chunk(
    text: str = (
        "Employees receive 20 days of annual leave per year."
    ),
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=101,
        document_id=7,
        organization_id=2,
        chunk_index=0,
        text=text,
        score=0.91,
        page_start=2,
        page_end=2,
        document_name="leave_policy.pdf",
    )


def test_generate_answer_uses_context():
    llm = FakeLLM()
    chunk = make_chunk()

    result = generate_answer(
        question=(
            "How many annual leave days do employees receive?"
        ),
        chunks=[chunk],
        llm_client=llm,
    )

    assert (
        result.answer
        == "Employees receive 20 days of annual leave per year."
    )

    assert result.sources == [chunk]

    assert (
        "How many annual leave days do employees receive?"
        in llm.user_prompt
    )

    assert (
        "Employees receive 20 days of annual leave per year."
        in llm.user_prompt
    )

    assert "Do not invent facts" in llm.system_prompt


def test_generate_answer_rejects_empty_question():
    llm = FakeLLM()

    with pytest.raises(
        ValueError,
        match="Question cannot be empty",
    ):
        generate_answer(
            question="   ",
            chunks=[make_chunk()],
            llm_client=llm,
        )


def test_generate_answer_abstains_without_context():
    llm = FakeLLM()

    result = generate_answer(
        question="What is not in the documents?",
        chunks=[],
        llm_client=llm,
    )

    assert (
        "do not contain enough information"
        in result.answer
    )

    assert result.sources == []
    assert llm.user_prompt is None


def test_generate_answer_rejects_empty_llm_response():
    class EmptyLLM:
        def generate(
            self,
            *,
            system_prompt: str,
            user_prompt: str,
        ) -> str:
            return "   "

    with pytest.raises(
        LLMGenerationError,
        match="empty answer",
    ):
        generate_answer(
            question="What is the answer?",
            chunks=[make_chunk()],
            llm_client=EmptyLLM(),
        )


def test_generate_answer_numbers_context_passages():
    llm = FakeLLM()

    first = make_chunk(text="First annual leave clause.")
    second = make_chunk(text="Second remote work clause.")

    generate_answer(
        question="What do the policies say?",
        chunks=[first, second],
        llm_client=llm,
    )

    assert "[1]\nFirst annual leave clause." in (
        llm.user_prompt
    )
    assert "[2]\nSecond remote work clause." in (
        llm.user_prompt
    )

    assert llm.user_prompt.index("[1]") < llm.user_prompt.index(
        "[2]"
    )


def test_generate_answer_prompt_instructs_inline_citations():
    llm = FakeLLM()

    generate_answer(
        question="What do the policies say?",
        chunks=[make_chunk()],
        llm_client=llm,
    )

    assert "bracketed number" in llm.system_prompt
    assert "inline" in llm.system_prompt
    assert "Do not invent facts" in llm.system_prompt


def test_generate_answer_preserves_inline_citation_markers():
    class CitingLLM:
        def generate(
            self,
            *,
            system_prompt: str,
            user_prompt: str,
        ) -> str:
            return (
                "Employees receive 20 days of annual "
                "leave per year [1]."
            )

    result = generate_answer(
        question="How many annual leave days?",
        chunks=[make_chunk()],
        llm_client=CitingLLM(),
    )

    assert result.answer.endswith("[1].")
    assert len(result.sources) == 1
