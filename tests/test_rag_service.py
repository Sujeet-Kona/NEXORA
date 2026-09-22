from backend.db.database import SessionLocal
from backend.repositories.qdrant_repository import QdrantRepository
from backend.services.embedding_service import EmbeddingService
from backend.services.llm.base import LLMClient
from backend.services.rag_service import answer_question
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
