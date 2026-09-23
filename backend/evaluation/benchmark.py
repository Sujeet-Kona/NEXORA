"""Retrieval quality benchmark.

Offline mode (default) benchmarks BM25 over the labeled corpus without a
database or vector store, comparing the pre-Phase-10 BM25 behavior
(whitespace tokenizer, zero-score chunks kept) with the current one.

Live mode (--live) seeds a fresh organization in Postgres and Qdrant
through the production document pipeline (extraction, chunking, bge-m3
embeddings, Qdrant indexing), then compares BM25, dense, RRF-fused
hybrid, and the full hybrid pipeline (cross-encoder rerank) on the same
labeled cases. All seeded data is removed afterwards.

Usage:
    .venv/bin/python -m backend.evaluation.benchmark
    .venv/bin/python -m backend.evaluation.benchmark --live
"""

import argparse
import shutil
from uuid import uuid4

from qdrant_client import models
from rank_bm25 import BM25Okapi

from backend.core.config import settings
from backend.db.database import SessionLocal
from backend.db.models import (
    Document,
    DocumentChunk,
    Organization,
    OrganizationMembership,
    User,
)
from backend.evaluation.dataset import (
    BENCHMARK_DATA_DIR,
    DOCX_CONTENT_TYPE,
    build_corpus_chunks,
    ground_truth_chunk_ids,
    load_cases,
)
from backend.evaluation.metrics import (
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)
from backend.repositories.document_repository import (
    create_document_pending,
    finalize_document_upload,
)
from backend.repositories.qdrant_repository import QdrantRepository
from backend.repositories.user_repository import create_user
from backend.services.bm25_service import (
    BM25Index,
    invalidate_bm25_index,
)
from backend.services.document_processing_service import (
    process_document,
)
from backend.services.embedding_service import EmbeddingService
from backend.services.hybrid_retrieval_service import (
    _rrf_fuse,
    get_reranker,
    hybrid_retrieve_chunks,
)
from backend.services.organization_service import (
    create_organization_service,
)
from backend.services.retrievers import (
    DenseRetriever,
    LexicalRetriever,
)
from backend.services.storage import LocalStorage

K = 10


def evaluate_config(
    name: str,
    rankings: list[list[int]],
    ground_truths: list[set[int]],
) -> dict:
    case_count = len(ground_truths)

    return {
        "name": name,
        "recall_1": sum(
            recall_at_k(gt, ranking, 1)
            for gt, ranking in zip(ground_truths, rankings)
        )
        / case_count,
        "recall_5": sum(
            recall_at_k(gt, ranking, 5)
            for gt, ranking in zip(ground_truths, rankings)
        )
        / case_count,
        "recall_10": sum(
            recall_at_k(gt, ranking, 10)
            for gt, ranking in zip(ground_truths, rankings)
        )
        / case_count,
        "precision_10": sum(
            precision_at_k(gt, ranking, 10)
            for gt, ranking in zip(ground_truths, rankings)
        )
        / case_count,
        "mrr": sum(
            reciprocal_rank(gt, ranking)
            for gt, ranking in zip(ground_truths, rankings)
        )
        / case_count,
    }


def print_summary(results: list[dict]) -> None:
    print("=" * 78)
    print(
        f"{'config':<14}"
        f"{'Recall@1':>10}"
        f"{'Recall@5':>10}"
        f"{'Recall@10':>11}"
        f"{'Prec@10':>9}"
        f"{'MRR':>8}"
    )

    for result in results:
        print(
            f"{result['name']:<14}"
            f"{result['recall_1']:>10.4f}"
            f"{result['recall_5']:>10.4f}"
            f"{result['recall_10']:>11.4f}"
            f"{result['precision_10']:>9.4f}"
            f"{result['mrr']:>8.4f}"
        )


def _legacy_tokenize(text: str) -> list[str]:
    return text.lower().split()


def run_offline() -> None:
    cases = load_cases()
    chunks = build_corpus_chunks()

    print("Corpus documents:", len({
        chunk.document_name for chunk in chunks
    }))
    print("Corpus chunks:", len(chunks))
    print("Evaluation questions:", len(cases))

    index = BM25Index(chunks)
    legacy = BM25Okapi(
        [_legacy_tokenize(chunk.text) for chunk in chunks]
    )

    ground_truths: list[set[int]] = []
    legacy_rankings: list[list[int]] = []
    bm25_rankings: list[list[int]] = []

    for case in cases:
        relevant = ground_truth_chunk_ids(chunks, case)

        if not relevant:
            raise RuntimeError(
                "Ground truth not found for: "
                + case.question
            )

        legacy_scores = legacy.get_scores(
            _legacy_tokenize(case.question)
        )

        legacy_ranked = sorted(
            zip(chunks, legacy_scores),
            key=lambda item: float(item[1]),
            reverse=True,
        )

        legacy_rankings.append(
            [
                chunk.id
                for chunk, _ in legacy_ranked[:K]
            ]
        )

        bm25_rankings.append(
            [
                chunk.id
                for chunk, _ in index.search(
                    query=case.question,
                    limit=K,
                )
            ]
        )

        ground_truths.append(relevant)

        print("=" * 78)
        print("Question:", case.question)
        print("Relevant chunk IDs:", sorted(relevant))
        print("Legacy BM25 top-10:", legacy_rankings[-1])
        print("BM25 top-10:", bm25_rankings[-1])

    print_summary(
        [
            evaluate_config(
                "bm25_legacy",
                legacy_rankings,
                ground_truths,
            ),
            evaluate_config(
                "bm25",
                bm25_rankings,
                ground_truths,
            ),
        ]
    )


def _seed_live_corpus(
    db,
    storage: LocalStorage,
    embedding_service: EmbeddingService,
    qdrant_repository: QdrantRepository,
    organization_id: int,
    user_id: int,
) -> None:
    for path in sorted(BENCHMARK_DATA_DIR.glob("*.docx")):
        content = path.read_bytes()

        document = create_document_pending(
            db=db,
            organization_id=organization_id,
            uploaded_by=user_id,
            name=path.name,
        )

        storage_key = storage.save(
            organization_id,
            document.id,
            path.name,
            content,
        )

        finalize_document_upload(
            db=db,
            document=document,
            storage_key=storage_key,
            file_size=len(content),
            content_type=DOCX_CONTENT_TYPE,
        )

        process_document(
            db=db,
            document_id=document.id,
            embedding_service=embedding_service,
            qdrant_repository=qdrant_repository,
        )

        db.expire(document)

        print(
            "Processed:",
            path.name,
            "document_id=" + str(document.id),
            "status=" + str(document.status),
        )


def _cleanup_live_corpus(
    db,
    qdrant_repository: QdrantRepository,
    storage: LocalStorage,
    organization_id: int,
    user_id: int,
) -> None:
    documents = (
        db.query(Document)
        .filter(
            Document.organization_id == organization_id,
        )
        .all()
    )

    for document in documents:
        qdrant_repository.delete_document_chunks(
            document_id=document.id,
            organization_id=organization_id,
        )

        if document.storage_key:
            storage.delete(document.storage_key)

    db.query(DocumentChunk).filter(
        DocumentChunk.organization_id == organization_id,
    ).delete(synchronize_session=False)

    db.query(Document).filter(
        Document.organization_id == organization_id,
    ).delete(synchronize_session=False)

    db.query(OrganizationMembership).filter(
        OrganizationMembership.organization_id
        == organization_id,
    ).delete(synchronize_session=False)

    db.query(Organization).filter(
        Organization.id == organization_id,
    ).delete(synchronize_session=False)

    db.query(User).filter(User.id == user_id).delete(
        synchronize_session=False,
    )

    db.commit()

    invalidate_bm25_index(organization_id)

    shutil.rmtree(
        storage.base_path / "organizations" / str(organization_id),
        ignore_errors=True,
    )

    leftover_documents = (
        db.query(Document)
        .filter(
            Document.organization_id == organization_id,
        )
        .count()
    )

    leftover_chunks = (
        db.query(DocumentChunk)
        .filter(
            DocumentChunk.organization_id == organization_id,
        )
        .count()
    )

    leftover_organizations = (
        db.query(Organization)
        .filter(Organization.id == organization_id)
        .count()
    )

    leftover_users = (
        db.query(User).filter(User.id == user_id).count()
    )

    qdrant_points = qdrant_repository.client.count(
        collection_name=settings.qdrant_collection,
        count_filter=models.Filter(
            must=[
                models.FieldCondition(
                    key="organization_id",
                    match=models.MatchValue(
                        value=organization_id,
                    ),
                ),
            ],
        ),
        exact=True,
    ).count

    print("=" * 78)
    print("Cleanup proof:")
    print("  leftover documents:", leftover_documents)
    print("  leftover chunks:", leftover_chunks)
    print("  leftover organizations:", leftover_organizations)
    print("  leftover users:", leftover_users)
    print("  leftover qdrant points:", qdrant_points)


def run_live() -> None:
    cases = load_cases()

    db = SessionLocal()
    embedding_service = EmbeddingService()
    qdrant_repository = QdrantRepository()
    storage = LocalStorage(settings.storage_path)

    organization_id = None
    user_id = None

    try:
        user = create_user(
            db=db,
            email=(
                "retrieval-benchmark-"
                + uuid4().hex[:8]
                + "@example.com"
            ),
            full_name="Retrieval Benchmark",
        )

        user_id = user.id

        organization = create_organization_service(
            db=db,
            name="Retrieval Benchmark Company",
            user_id=user_id,
        )

        organization_id = organization.id

        print("Organization ID:", organization_id)

        _seed_live_corpus(
            db=db,
            storage=storage,
            embedding_service=embedding_service,
            qdrant_repository=qdrant_repository,
            organization_id=organization_id,
            user_id=user_id,
        )

        documents = (
            db.query(Document)
            .filter(
                Document.organization_id == organization_id,
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
                == organization_id,
            )
            .order_by(
                DocumentChunk.document_id,
                DocumentChunk.chunk_index,
            )
            .all()
        )

        print("=" * 78)
        print("Benchmark documents:", len(documents))
        print("Benchmark chunks:", len(chunks))
        print("Evaluation questions:", len(cases))

        dense_retriever = DenseRetriever(
            embedding_service,
            qdrant_repository,
            limit=K,
        )

        lexical_retriever = LexicalRetriever(limit=K)

        try:
            get_reranker()
            reranker_available = True
        except Exception as exc:
            reranker_available = False
            print(
                "Cross-encoder reranker unavailable, "
                "skipping hybrid_full:",
                exc,
            )

        ground_truths: list[set[int]] = []
        rankings_by_config: dict[str, list[list[int]]] = {
            "bm25": [],
            "dense": [],
            "hybrid_rrf": [],
            "hybrid_full": [],
        }

        for case in cases:
            relevant = {
                chunk.id
                for chunk in chunks
                if document_names.get(chunk.document_id)
                == case.document
                and case.anchor in chunk.text
            }

            if not relevant:
                raise RuntimeError(
                    "Ground truth not found for: "
                    + case.question
                )

            dense = dense_retriever.retrieve(
                db=db,
                organization_id=organization_id,
                query=case.question,
            )

            lexical = lexical_retriever.retrieve(
                db=db,
                organization_id=organization_id,
                query=case.question,
            )

            dense_ids = [
                chunk.chunk_id for chunk in dense
            ]

            lexical_ids = [
                chunk.chunk_id for chunk in lexical
            ]

            fused_ids = [
                candidate.chunk.chunk_id
                for candidate in _rrf_fuse(
                    [dense, lexical],
                )[:K]
            ]

            ground_truths.append(relevant)

            rankings_by_config["bm25"].append(lexical_ids)
            rankings_by_config["dense"].append(dense_ids)
            rankings_by_config["hybrid_rrf"].append(
                fused_ids
            )

            if reranker_available:
                hybrid = hybrid_retrieve_chunks(
                    db=db,
                    organization_id=organization_id,
                    query=case.question,
                    embedding_service=embedding_service,
                    qdrant_repository=qdrant_repository,
                    rerank_limit=K,
                    final_limit=K,
                )

                rankings_by_config["hybrid_full"].append(
                    [
                        chunk.chunk_id
                        for chunk in hybrid
                    ]
                )

            print("=" * 78)
            print("Question:", case.question)
            print("Relevant chunk IDs:", sorted(relevant))
            print("BM25 top-10:", lexical_ids)
            print("Dense top-10:", dense_ids)
            print("Hybrid RRF top-10:", fused_ids)

            if reranker_available:
                print(
                    "Hybrid full top-10:",
                    rankings_by_config["hybrid_full"][-1],
                )

        print_summary(
            [
                evaluate_config(name, rankings, ground_truths)
                for name, rankings in rankings_by_config.items()
                if rankings
            ]
        )

    finally:
        if organization_id is not None:
            _cleanup_live_corpus(
                db=db,
                qdrant_repository=qdrant_repository,
                storage=storage,
                organization_id=organization_id,
                user_id=user_id,
            )

        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="NEXORA retrieval quality benchmark",
    )

    parser.add_argument(
        "--live",
        action="store_true",
        help=(
            "Seed a fresh organization through the "
            "production pipeline and benchmark against "
            "Postgres and Qdrant"
        ),
    )

    args = parser.parse_args()

    if args.live:
        run_live()
    else:
        run_offline()


if __name__ == "__main__":
    main()
