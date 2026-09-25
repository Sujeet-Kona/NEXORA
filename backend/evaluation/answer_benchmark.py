"""End-to-end answer quality benchmark.

Runs the labeled evaluation questions through the production query
pipeline -- hybrid retrieval (dense + BM25 + RRF), cross-encoder
rerank, then Ollama generation -- against live Postgres, Qdrant and
Ollama, and measures:

* fact accuracy     -- the expected fact appears in the answer
* citation accuracy -- a ground-truth chunk appears in the sources
* refusal rate      -- negative cases decline instead of fabricating
* latency           -- total pipeline time and generation time alone

Two retrieval widths are measured so the effect of context size on
answer quality is visible: the production default (RETRIEVAL_TOP_K)
and the width used by the Phase 10 retrieval baseline.

A fresh organization is seeded through the real document pipeline and
removed again when the run finishes.

Usage:
    .venv/bin/python -m backend.evaluation.answer_benchmark
"""

import time
from uuid import uuid4

from backend.core.config import settings
from backend.db.database import SessionLocal
from backend.db.models import Document, DocumentChunk
from backend.evaluation.benchmark import (
    cleanup_live_corpus,
    seed_live_corpus,
)
from backend.evaluation.dataset import (
    REFUSAL_MARKERS,
    load_cases,
    load_negative_cases,
)
from backend.evaluation.metrics import (
    fact_matches,
    indicates_refusal,
    latency_summary,
)
from backend.repositories.qdrant_repository import QdrantRepository
from backend.repositories.user_repository import create_user
from backend.services.embedding_service import EmbeddingService
from backend.services.llm.base import LLMClient
from backend.services.llm.ollama_client import OllamaLLMClient
from backend.services.organization_service import (
    create_organization_service,
)
from backend.services.rag_service import answer_question
from backend.services.storage import LocalStorage


class TimingLLMClient:
    """Delegates to an LLM client and records each call's duration."""

    def __init__(self, delegate: LLMClient):
        self._delegate = delegate
        self.last_elapsed: float | None = None

    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        start = time.perf_counter()

        try:
            return self._delegate.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        finally:
            self.last_elapsed = time.perf_counter() - start


def _relevant_chunk_ids(
    chunks,
    document_names: dict[int, str],
    case,
) -> set[int]:
    relevant = {
        chunk.id
        for chunk in chunks
        if document_names.get(chunk.document_id)
        == case.document
        and case.anchor in chunk.text
    }

    if not relevant:
        raise RuntimeError(
            "Ground truth not found for: " + case.question
        )

    return relevant


def _ask(
    *,
    db,
    organization_id: int,
    question: str,
    top_k: int,
    embedding_service: EmbeddingService,
    qdrant_repository: QdrantRepository,
    llm_client: OllamaLLMClient,
):
    timing_client = TimingLLMClient(llm_client)

    start = time.perf_counter()

    response = answer_question(
        db=db,
        organization_id=organization_id,
        question=question,
        embedding_service=embedding_service,
        qdrant_repository=qdrant_repository,
        llm_client=timing_client,
        retrieval_limit=top_k,
    )

    total_elapsed = time.perf_counter() - start

    return (
        response,
        total_elapsed,
        timing_client.last_elapsed or 0.0,
    )


def _format_latency(summary: dict[str, float]) -> str:
    return (
        "mean={mean:.2f}s median={median:.2f}s "
        "p95={p95:.2f}s min={min:.2f}s max={max:.2f}s"
    ).format(**summary)


def run_configuration(
    label: str,
    top_k: int,
    *,
    db,
    organization_id: int,
    embedding_service: EmbeddingService,
    qdrant_repository: QdrantRepository,
    llm_client: OllamaLLMClient,
    chunks,
    document_names: dict[int, str],
    cases,
    negative_cases,
) -> dict:
    print("=" * 78)
    print("Configuration:", label)
    print("=" * 78)

    fact_hits = 0
    citation_hits = 0
    refusal_hits = 0

    total_latencies: list[float] = []
    generation_latencies: list[float] = []

    for case in cases:
        relevant = _relevant_chunk_ids(
            chunks,
            document_names,
            case,
        )

        response, total_elapsed, generation_elapsed = _ask(
            db=db,
            organization_id=organization_id,
            question=case.question,
            top_k=top_k,
            embedding_service=embedding_service,
            qdrant_repository=qdrant_repository,
            llm_client=llm_client,
        )

        source_ids = [
            source.chunk_id for source in response.sources
        ]

        fact_ok = fact_matches(
            response.answer,
            case.expected,
        )

        citation_ok = bool(
            set(source_ids) & relevant
        )

        fact_hits += int(fact_ok)
        citation_hits += int(citation_ok)

        total_latencies.append(total_elapsed)
        generation_latencies.append(generation_elapsed)

        print("-" * 78)
        print("Q:", case.question)
        print(
            "  fact={} citation={} sources={} relevant={}".format(
                "OK" if fact_ok else "MISS",
                "OK" if citation_ok else "MISS",
                source_ids,
                sorted(relevant),
            )
        )
        print(
            "  total={:.2f}s generation={:.2f}s".format(
                total_elapsed,
                generation_elapsed,
            )
        )
        print("  answer:", repr(response.answer))

    for negative_case in negative_cases:
        response, total_elapsed, generation_elapsed = _ask(
            db=db,
            organization_id=organization_id,
            question=negative_case.question,
            top_k=top_k,
            embedding_service=embedding_service,
            qdrant_repository=qdrant_repository,
            llm_client=llm_client,
        )

        refused = indicates_refusal(
            response.answer,
            REFUSAL_MARKERS,
        )

        refusal_hits += int(refused)

        total_latencies.append(total_elapsed)
        generation_latencies.append(generation_elapsed)

        print("-" * 78)
        print(
            "Q (negative, topic={}): {}".format(
                negative_case.topic,
                negative_case.question,
            )
        )
        print(
            "  refusal={} sources={}".format(
                "OK" if refused else "FABRICATED",
                [
                    source.chunk_id
                    for source in response.sources
                ],
            )
        )
        print("  answer:", repr(response.answer))

    total_count = len(cases)
    negative_count = len(negative_cases)

    result = {
        "label": label,
        "top_k": top_k,
        "questions": total_count,
        "fact_hits": fact_hits,
        "fact_accuracy": fact_hits / total_count,
        "citation_hits": citation_hits,
        "citation_accuracy": citation_hits / total_count,
        "negative_questions": negative_count,
        "refusal_hits": refusal_hits,
        "refusal_rate": (
            refusal_hits / negative_count
            if negative_count
            else 0.0
        ),
        "total_latency": latency_summary(total_latencies),
        "generation_latency": latency_summary(
            generation_latencies
        ),
    }

    print("-" * 78)
    print(
        "Fact accuracy:     {}/{} = {:.4f}".format(
            fact_hits,
            total_count,
            result["fact_accuracy"],
        )
    )
    print(
        "Citation accuracy: {}/{} = {:.4f}".format(
            citation_hits,
            total_count,
            result["citation_accuracy"],
        )
    )
    print(
        "Refusal rate:      {}/{} = {:.4f}".format(
            refusal_hits,
            negative_count,
            result["refusal_rate"],
        )
    )
    print(
        "Latency total:      ",
        _format_latency(result["total_latency"]),
    )
    print(
        "Latency generation: ",
        _format_latency(result["generation_latency"]),
    )

    return result


def print_comparison(results: list[dict]) -> None:
    print("=" * 78)
    print("SUMMARY")
    print("=" * 78)

    header = (
        "{:<34}{:>8}{:>10}{:>9}{:>10}{:>10}"
    ).format(
        "configuration",
        "fact",
        "citation",
        "refusal",
        "total p95",
        "gen mean",
    )

    print(header)
    print("-" * len(header))

    for result in results:
        print(
            "{:<34}{:>8.4f}{:>10.4f}{:>9.4f}{:>9.2f}s{:>9.2f}s"
            .format(
                result["label"],
                result["fact_accuracy"],
                result["citation_accuracy"],
                result["refusal_rate"],
                result["total_latency"]["p95"],
                result["generation_latency"]["mean"],
            )
        )


def run() -> None:
    cases = load_cases()
    negative_cases = load_negative_cases()

    db = SessionLocal()
    embedding_service = EmbeddingService()
    qdrant_repository = QdrantRepository()
    storage = LocalStorage(settings.storage_path)
    llm_client = OllamaLLMClient()

    organization_id = None
    user_id = None

    configurations = [
        (
            "top_k={} (production default)".format(
                settings.retrieval_top_k
            ),
            settings.retrieval_top_k,
        ),
        ("top_k=10 (Phase 10 baseline K)", 10),
    ]

    try:
        user = create_user(
            db=db,
            email=(
                "answer-benchmark-"
                + uuid4().hex[:8]
                + "@example.com"
            ),
            full_name="Answer Benchmark",
        )

        user_id = user.id

        organization = create_organization_service(
            db=db,
            name="Answer Benchmark Company",
            user_id=user_id,
        )

        organization_id = organization.id

        print("Organization ID:", organization_id)
        print(
            "LLM model:",
            llm_client.model,
            "| num_predict:",
            llm_client.num_predict,
            "| think:",
            llm_client.think,
            "| timeout:",
            llm_client.timeout,
        )

        seed_live_corpus(
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
                Document.organization_id
                == organization_id,
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

        print("Corpus documents:", len(documents))
        print("Corpus chunks:", len(chunks))
        print("Questions:", len(cases))
        print("Negative questions:", len(negative_cases))

        results = [
            run_configuration(
                label,
                top_k,
                db=db,
                organization_id=organization_id,
                embedding_service=embedding_service,
                qdrant_repository=qdrant_repository,
                llm_client=llm_client,
                chunks=chunks,
                document_names=document_names,
                cases=cases,
                negative_cases=negative_cases,
            )
            for label, top_k in configurations
        ]

        print_comparison(results)

    finally:
        if organization_id is not None and user_id is not None:
            cleanup_live_corpus(
                db=db,
                qdrant_repository=qdrant_repository,
                storage=storage,
                organization_id=organization_id,
                user_id=user_id,
            )

        db.close()


def main() -> None:
    run()


if __name__ == "__main__":
    main()
