# NEXORA

[![CI](https://github.com/Sujeet-Kona/NEXORA/actions/workflows/ci.yml/badge.svg)](https://github.com/Sujeet-Kona/NEXORA/actions/workflows/ci.yml)

**A multi-tenant retrieval-augmented generation platform** built as a FastAPI modular monolith. NEXORA ingests PDF and DOCX documents, retrieves evidence through lexical and dense search, and produces cited answers through a local LLM runtime. If retrieval does not return sufficient evidence, the system refuses before generation.

> **Scope:** NEXORA is a production-oriented engineering project, not a claim of a deployed or fully managed SaaS product. The retrieval metrics below apply only to the documented 16-document benchmark corpus; they are not production SLAs or universal answer-accuracy claims.

## Capabilities

- PDF/DOCX ingestion and document versioning.
- BGE-M3 dense embeddings and BM25 lexical retrieval.
- Reciprocal Rank Fusion (RRF) and cross-encoder reranking.
- Relevance filtering, grounded citations, and SSE response streaming.
- Tenant-scoped authorization across application and retrieval data.
- Deterministic refusal when sufficient evidence is unavailable.
- Explicit document lifecycle states, stale-processing recovery, and database locking.

## Architecture

NEXORA separates API handling, authentication, tenant authorization, document lifecycle, retrieval, generation, and evaluation.

~~~mermaid
flowchart LR
    CLIENT[Client] --> API[FastAPI]
    API --> AUTH[JWT / RBAC / tenant scope]
    AUTH --> INGEST[Document ingestion]
    AUTH --> QUERY[Question answering]
    INGEST --> PG[(PostgreSQL)]
    INGEST --> FILES[Local document storage]
    INGEST --> EMB[BGE-M3 embeddings]
    EMB --> QD[(Qdrant)]
    QUERY --> BM25[BM25 retrieval]
    QUERY --> DENSE[Dense retrieval]
    BM25 --> RRF[RRF fusion]
    DENSE --> RRF
    RRF --> RERANK[Cross-encoder reranking]
    RERANK --> GATE{Sufficient evidence?}
    GATE -->|No| REFUSE[Deterministic refusal]
    GATE -->|Yes| LLM[Ollama LLM]
    LLM --> CITATIONS[Validated citations]
    CITATIONS --> SSE[SSE response]
~~~

### Component responsibilities

| Component | Responsibility |
|---|---|
| PostgreSQL | Authoritative users, organizations, documents, versions, chunks, lifecycle state, and audit records |
| Qdrant | Dense-vector index and retrieval candidates; not the source of truth |
| Local storage | Uploaded source documents |
| BGE-M3 | Query and document-chunk embeddings |
| BM25 | Lexical retrieval |
| Cross-encoder | Candidate relevance scoring and threshold filtering |
| Ollama | Local answer generation after evidence checks |

The core retrieval orchestration, rank fusion, authorization, lifecycle handling, and evaluation are implemented in the repository's Python services. The project uses langchain-text-splitters for text splitting; LangChain/LangGraph are not the core orchestration layer.

## Request and retrieval flow

1. Validate the request and authenticate the caller.
2. Resolve the caller's organization and enforce role/tenant permissions.
3. Run BM25 and dense Qdrant retrieval within the tenant scope.
4. Fuse rankings with equal-weight RRF.
5. Rerank the candidate pool with cross-encoder/ms-marco-MiniLM-L-6-v2.
6. Remove candidates below the configured relevance threshold.
7. If no usable evidence remains, return a deterministic refusal without calling the LLM.
8. Otherwise generate from selected evidence, validate citation references, and stream the response through SSE.

### Document lifecycle and reliability

Documents move through explicit PENDING, PROCESSING, READY, and FAILED states. Failed work can be retried; stale processing can be recovered. PostgreSQL row locking protects processing claims and conflicting replacement/deletion operations. Tenant scope is enforced in PostgreSQL and Qdrant, and retrieved hits are checked against authoritative document/chunk state before text is exposed.

Security controls include JWT access tokens, refresh-token rotation and revocation, JTI denylisting, Argon2 password hashing, login throttling, upload size/type/signature validation, guarded local file storage, static error responses, request IDs, and allowlisted audit details.

**Consistency boundary:** PostgreSQL and Qdrant do not participate in a single distributed transaction. A process failure can leave stale external index state in some failure windows; retrieval excludes chunks belonging to documents that are not READY. The implementation does not claim perfect two-phase consistency.

## Live retrieval evaluation

The live benchmark seeds an isolated benchmark organization, runs the normal ingestion/indexing path, evaluates labeled questions, and removes the temporary benchmark data.

**Benchmark size:** 16 documents · 220 chunks · 60 labeled retrieval questions.

| Configuration | Recall@1 | Recall@5 | Recall@10 | Precision@10 | MRR |
|---|---:|---:|---:|---:|---:|
| BM25 | **66.67%** | 86.67% | 95.00% | 9.50% | **0.7483** |
| Dense | 63.33% | 86.67% | **100.00%** | 10.00% | 0.7334 |
| Hybrid RRF | 63.33% | **93.33%** | **100.00%** | 10.00% | 0.7481 |
| Hybrid + reranker | 63.33% | **93.33%** | **100.00%** | 10.00% | 0.7440 |
| Hybrid Full | 63.33% | 83.33% | 85.00% | 8.50% | 0.7056 |

### Interpretation

- Best Recall@1 in this run: **66.67%** (BM25).
- Hybrid RRF achieved **93.33% Recall@5** and **100.00% Recall@10**.
- The reranker did **not** improve the reported aggregate benchmark: MRR was 0.7481 for RRF and 0.7440 after reranking.
- Recall and precision are retrieval metrics, not answer accuracy.
- Results describe this small, controlled corpus only.

The completed run verified cleanup of all temporary benchmark entities:

~~~text
leftover documents      = 0
leftover chunks         = 0
leftover organizations  = 0
leftover users          = 0
leftover Qdrant points  = 0
~~~

See [Evaluation](docs/evaluation.md) for methodology, reproduction steps, limitations, and historical results.

## Technology

| Area | Stack |
|---|---|
| Language / API | Python, FastAPI, Starlette, Uvicorn |
| Validation / configuration | Pydantic v2, pydantic-settings |
| Database / migrations | PostgreSQL 17, SQLAlchemy 2.0, Alembic |
| Vector retrieval | Qdrant, BGE-M3 |
| Lexical retrieval | BM25 / rank-bm25 |
| Reranking | sentence-transformers cross-encoder |
| Local inference | Ollama |
| Documents | PyMuPDF, python-docx |
| Testing / delivery | pytest, Docker, Docker Compose, GitHub Actions |

## Web interface

NEXORA includes a lightweight, same-origin web client served by FastAPI at `/`.
It provides account registration/sign-in, organization selection and creation,
PDF/DOCX upload, document lifecycle visibility, streamed RAG chat, and retrieved
source references. The client calls the existing versioned API; the only API
addition for the interface is an authenticated, membership-scoped
`GET /api/v1/organizations` listing.

Run the backend using the normal setup instructions, then open
`http://127.0.0.1:8000/`. No separate frontend development server or CORS
configuration is required. Access tokens are kept in page memory rather than
browser local storage; refreshing the page requires signing in again.

The interface respects the API's existing tenant and role checks. It does not
provide an alternate authorization path or bypass document processing.

## Repository guide

- [Architecture](docs/architecture.md) — components, request paths, ingestion and query flows.
- [Evaluation](docs/evaluation.md) — benchmark protocol, metrics, results, and limitations.
- backend/api/ — HTTP endpoints and SSE entry points.
- backend/services/ — ingestion, retrieval, generation, and lifecycle logic.
- backend/repositories/ — persistence and tenant-scoped data access.
- backend/evaluation/ — benchmark datasets and runners.

## Explicit limitations

- OCR for scanned/image-only PDFs is not implemented.
- Image understanding is not implemented.
- Retrieval benchmark results do not establish answer correctness or production performance.
- The reranker has not shown an aggregate improvement in the reported benchmark.
- The application is not represented as a deployed, managed production SaaS service.
