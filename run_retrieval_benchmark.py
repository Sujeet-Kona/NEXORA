from backend.db.database import SessionLocal
from backend.db.models import Document, DocumentChunk

from backend.repositories.qdrant_repository import QdrantRepository
from backend.services.embedding_service import EmbeddingService
from backend.services.retrieval_service import retrieve_chunks

from retrieval_benchmark_cases import EVALUATION_CASES


ORGANIZATION_ID = 2


def main():
    db = SessionLocal()

    try:
        documents = (
            db.query(Document)
            .filter(
                Document.organization_id == ORGANIZATION_ID
            )
            .all()
        )

        document_names = {
            document.id: document.name
            for document in documents
        }

        chunks = (
            db.query(DocumentChunk)
            .filter(
                DocumentChunk.organization_id
                == ORGANIZATION_ID
            )
            .order_by(
                DocumentChunk.document_id,
                DocumentChunk.chunk_index,
            )
            .all()
        )

        embedding_service = EmbeddingService()
        qdrant_repository = QdrantRepository()

        print("Benchmark documents:", len(documents))
        print("Benchmark chunks:", len(chunks))
        print("Evaluation questions:", len(EVALUATION_CASES))

        recall_1 = []
        recall_5 = []
        recall_10 = []
        reciprocal_ranks = []

        for case in EVALUATION_CASES:
            relevant_ids = {
                chunk.id
                for chunk in chunks
                if (
                    document_names.get(chunk.document_id)
                    == case["document"]
                    and case["anchor"] in chunk.text
                )
            }

            if not relevant_ids:
                raise RuntimeError(
                    "Ground truth not found for: "
                    + case["question"]
                )

            results = retrieve_chunks(
                db=db,
                organization_id=ORGANIZATION_ID,
                query=case["question"],
                embedding_service=embedding_service,
                qdrant_repository=qdrant_repository,
                limit=10,
            )

            retrieved_ids = [
                result.chunk_id
                for result in results
            ]

            relevant_rank = None

            for rank, chunk_id in enumerate(
                retrieved_ids,
                start=1,
            ):
                if chunk_id in relevant_ids:
                    relevant_rank = rank
                    break

            r1 = int(
                any(
                    chunk_id in relevant_ids
                    for chunk_id in retrieved_ids[:1]
                )
            )

            r5 = int(
                any(
                    chunk_id in relevant_ids
                    for chunk_id in retrieved_ids[:5]
                )
            )

            r10 = int(
                any(
                    chunk_id in relevant_ids
                    for chunk_id in retrieved_ids[:10]
                )
            )

            rr = (
                1.0 / relevant_rank
                if relevant_rank is not None
                else 0.0
            )

            recall_1.append(r1)
            recall_5.append(r5)
            recall_10.append(r10)
            reciprocal_ranks.append(rr)

            print("=" * 90)
            print("Question:", case["question"])
            print("Document:", case["document"])
            print(
                "Relevant chunk IDs:",
                sorted(relevant_ids),
            )
            print("Retrieved:", retrieved_ids)
            print("First relevant rank:", relevant_rank)

        print("=" * 90)
        print(
            "Recall@1:",
            round(
                sum(recall_1) / len(recall_1),
                4,
            ),
        )
        print(
            "Recall@5:",
            round(
                sum(recall_5) / len(recall_5),
                4,
            ),
        )
        print(
            "Recall@10:",
            round(
                sum(recall_10) / len(recall_10),
                4,
            ),
        )
        print(
            "MRR:",
            round(
                sum(reciprocal_ranks)
                / len(reciprocal_ranks),
                4,
            ),
        )

    finally:
        db.close()


if __name__ == "__main__":
    main()
