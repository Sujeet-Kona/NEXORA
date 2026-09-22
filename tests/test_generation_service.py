import pytest

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
        RuntimeError,
        match="empty answer",
    ):
        generate_answer(
            question="What is the answer?",
            chunks=[make_chunk()],
            llm_client=EmptyLLM(),
        )
