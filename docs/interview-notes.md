# Interview Notes

Talking points for explaining NEXORA in a technical interview. Keep claims
aligned with the current implementation and measured results.

## 30-second pitch

"NEXORA is a secure, multi-tenant enterprise RAG platform. Tenants upload PDF
or DOCX documents; the system extracts and chunks the text, embeds it with
BGE-M3 into Qdrant, and answers questions using hybrid retrieval — dense vectors
plus BM25, fused with Reciprocal Rank Fusion and evaluated with a cross-encoder
reranker. Answers are grounded with citations and deterministic refusal when no
relevant evidence survives the retrieval threshold. It is a FastAPI modular
monolith with JWT authentication, Argon2 password hashing, organization-level
RBAC, tenant isolation, document lifecycle recovery, and audit logging."

## Architecture decisions worth defending

- **Modular monolith:** the project does not need microservices or distributed
  infrastructure for its current workload. The API, services, repositories, and
  stores have clear boundaries while remaining simple to test and operate.
- **PostgreSQL as source of truth:** ownership, metadata, chunk text, and audit
  records live in PostgreSQL. Qdrant is treated as a vector index, not as the
  authority for tenant ownership.
- **Hybrid retrieval:** BM25 handles exact terms and identifiers while dense
  retrieval handles semantic similarity. RRF combines ranked lists without
  requiring score normalization.
- **Custom RAG flow:** no LangChain/LangGraph core. The retrieval, grounding,
  citation, and evaluation logic is implemented directly so the behavior is
  explicit and testable.

## Hard problems and how they were solved

1. **Grounding:** deterministic no-context refusal plus a grounded LLM prompt,
   with citation validation after generation.
2. **Tenant isolation:** organization scoping across API/service/Postgres/Qdrant
   plus a Postgres re-check of returned vector hits.
3. **Authentication security:** Argon2 password hashing, required JWT expiry,
   rotating/revocable refresh tokens, JTI denylisting, and login throttling.
4. **Document lifecycle:** row locking around processing/replacement/deletion,
   stale `PROCESSING` recovery, and explicit retry handling for failed documents.
5. **Evaluation cleanup:** live retrieval evaluation seeds temporary data and
   proves that Postgres and Qdrant contain zero benchmark leftovers afterward.

## Current evaluation numbers

The current live retrieval benchmark uses **16 documents, 220 chunks, and 60
evaluation questions**.

- **Best Recall@1:** 0.6667 (BM25)
- **Best Recall@5:** 0.9333 (Hybrid RRF / Hybrid + reranker)
- **Best Recall@10:** 1.0000 (Dense / Hybrid RRF / Hybrid + reranker)
- **Best MRR:** 0.7483 (BM25)
- **Cleanup:** 0 leftover documents, chunks, organizations, users, or Qdrant
  points

### Important interview answer: did reranking help?

"Not on the current benchmark. Hybrid RRF reached 93.33% Recall@5 and 100%
Recall@10, while the cross-encoder produced the same Recall@1/5/10 and a slightly
lower MRR of 0.7440 versus RRF's 0.7481. I report that result instead of claiming
an improvement that the benchmark does not show."

That is the correct engineering answer.

## Metrics explained simply

- **Recall@1:** whether the relevant evidence is in the first result.
- **Recall@5:** whether the relevant evidence is somewhere in the first five.
- **MRR:** how high the first relevant result is ranked on average.
- **Precision@10:** how much of the first ten results is relevant.

Do not describe Recall@5 as answer accuracy.

## Security talking points

Argon2 password hashing; JWT with required expiry; refresh-token rotation and
revocation; JTI denylisting; login throttling; RBAC; tenant-scoped Postgres and
Qdrant access; upload size/type/magic-byte validation; guarded local storage;
parameterized database access; static error messages; request IDs without
logging secrets; append-only audit logging; production configuration validation.

## Honest limitations

- The retrieval dataset is controlled and still small compared with a real
  enterprise corpus.
- The current benchmark does not prove that the reranker improves retrieval.
- Local model latency is hardware-dependent and is not a production SLA.
- Local disk storage would need shared/persistent object storage for a
  multi-replica deployment.
- FastAPI BackgroundTasks are not a durable distributed queue.
- Login throttling is process-local; a shared rate-limit store would be needed
  for a multi-replica deployment.
- No OCR or image-only document understanding is claimed.

## Likely follow-up questions

**Why hybrid retrieval?**

"BM25 is strong for exact terms and identifiers; dense retrieval handles
paraphrases and semantic similarity. RRF combines their rankings without needing
their raw scores to be comparable."

**Why not just use a vector database?**

"Vector search is useful but does not replace lexical matching for exact names,
IDs, and policy terminology. The two approaches cover different failure modes."

**How do you prevent cross-tenant leakage?**

"Every retrieval path is organization-scoped, and Qdrant results are re-checked
against PostgreSQL before their text is returned. Qdrant is treated as an index,
not the source of truth."

**How do you stop hallucinations?**

"A relevance threshold can produce a deterministic no-LLM refusal, and the
normal generation path uses a grounded prompt plus citation validation."

**Why a monolith?**

"The current workload does not justify distributed infrastructure. A modular
monolith keeps the security and data flow easier to reason about while retaining
clean service boundaries."

**What would you add for a larger production deployment?**

"Shared rate limiting, object storage, a durable ingestion queue, distributed
observability, load testing, and operational controls — but only when the actual
scale and reliability requirements justify them."
