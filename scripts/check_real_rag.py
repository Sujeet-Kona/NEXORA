import time

from backend.db.database import SessionLocal
from backend.repositories.document_chunk_repository import (
    get_chunks_by_ids_for_organization,
)
from backend.repositories.qdrant_repository import QdrantRepository
from backend.services.embedding_service import EmbeddingService
from backend.services.generation_service import generate_answer
from backend.services.llm.ollama_client import OllamaLLMClient
from backend.services.retrieval_service import RetrievedChunk


ORGANIZATION_ID = 2
QUESTION = "How many days of annual leave do employees receive?"


def main() -> None:
    total_start = time.perf_counter()

    model_start = time.perf_counter()
    embedding_service = EmbeddingService()
    model_init_ms = (
        time.perf_counter() - model_start
    ) * 1000

    qdrant_repository = QdrantRepository()
    llm_client = OllamaLLMClient()

    db = SessionLocal()

    try:
        embedding_start = time.perf_counter()

        query_vector = embedding_service.embed_query(
            QUESTION
        )

        embedding_ms = (
            time.perf_counter() - embedding_start
        ) * 1000

        qdrant_start = time.perf_counter()

        search_result = qdrant_repository.search(
            query_vector=query_vector,
            organization_id=ORGANIZATION_ID,
            limit=2,
        )

        qdrant_ms = (
            time.perf_counter() - qdrant_start
        ) * 1000

        point_ids = [
            int(point.id)
            for point in search_result.points
        ]

        database_start = time.perf_counter()

        chunks = get_chunks_by_ids_for_organization(
            db=db,
            chunk_ids=point_ids,
            organization_id=ORGANIZATION_ID,
        )

        database_ms = (
            time.perf_counter() - database_start
        ) * 1000

        chunks_by_id = {
            chunk.id: chunk
            for chunk in chunks
        }

        retrieved = []

        for point in search_result.points:
            chunk = chunks_by_id.get(
                int(point.id)
            )

            if chunk is None:
                continue

            retrieved.append(
                RetrievedChunk(
                    chunk_id=chunk.id,
                    document_id=chunk.document_id,
                    organization_id=chunk.organization_id,
                    chunk_index=chunk.chunk_index,
                    text=chunk.text,
                    score=float(point.score),
                )
            )

        generation_start = time.perf_counter()

        generated = generate_answer(
            question=QUESTION,
            chunks=retrieved,
            llm_client=llm_client,
        )

        generation_ms = (
            time.perf_counter() - generation_start
        ) * 1000

        total_ms = (
            time.perf_counter() - total_start
        ) * 1000

        print("=" * 80)
        print("Answer:")
        print(generated.answer)
        print("=" * 80)
        print("Latency")
        print("-" * 80)
        print(
            "BGE initialization:",
            round(model_init_ms, 2),
            "ms",
        )
        print(
            "Query embedding:",
            round(embedding_ms, 2),
            "ms",
        )
        print(
            "Qdrant search:",
            round(qdrant_ms, 2),
            "ms",
        )
        print(
            "Database lookup:",
            round(database_ms, 2),
            "ms",
        )
        print(
            "Generation:",
            round(generation_ms, 2),
            "ms",
        )
        print(
            "Total:",
            round(total_ms, 2),
            "ms",
        )

    finally:
        db.close()


if __name__ == "__main__":
    main()
