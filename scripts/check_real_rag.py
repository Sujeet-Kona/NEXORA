from backend.db.database import SessionLocal
from backend.repositories.qdrant_repository import QdrantRepository
from backend.services.embedding_service import EmbeddingService
from backend.services.llm.ollama_client import OllamaLLMClient
from backend.services.rag_service import answer_question


ORGANIZATION_ID = 2

QUESTION = (
    "How many days of annual leave do employees receive?"
)


def main() -> None:
    db = SessionLocal()

    try:
        result = answer_question(
            db=db,
            organization_id=ORGANIZATION_ID,
            question=QUESTION,
            embedding_service=EmbeddingService(),
            qdrant_repository=QdrantRepository(),
            llm_client=OllamaLLMClient(),
            retrieval_limit=2,
        )

        print("=" * 80)
        print("Question:")
        print(QUESTION)
        print("=" * 80)

        print("Answer:")
        print(result.answer)

        print("=" * 80)
        print("Sources:", len(result.sources))

        for source in result.sources:
            print("-" * 80)
            print(
                "Document ID:",
                source.document_id,
            )
            print(
                "Chunk ID:",
                source.chunk_id,
            )
            print(
                "Chunk index:",
                source.chunk_index,
            )
            print(
                "Score:",
                round(source.score, 6),
            )
            print(source.text[:1000])

    finally:
        db.close()


if __name__ == "__main__":
    main()

