# Architecture

This document explains how NEXORA is built, in simple English. It describes
what the code actually does today, not future plans.

## What NEXORA is

NEXORA is a secure, multi-tenant "Enterprise RAG" platform. RAG stands for
**Retrieval-Augmented Generation**: instead of letting a language model answer
from memory, the system first **retrieves** the relevant pieces of your own
documents and then asks the model to answer **using only those pieces**, with
citations back to the source.

It is a **modular monolith**: one deployable FastAPI application, split into
clear internal layers and modules. There are no microservices, no message
broker, and no orchestration framework. This is a deliberate choice — the
workload (document Q&A for a bounded number of tenants) does not require
distributed infrastructure, and a single process is simpler to secure, deploy,
and reason about.

## The layered request path

```
Client (browser / API caller)
        │  HTTP + Bearer JWT
        ▼
FastAPI app (backend/main.py)
        │  RequestObservabilityMiddleware (adds X-Request-ID)
        │  CORS (only if configured)
        ▼
API routers (backend/api/v1/*)      ← request/response shapes (Pydantic)
        ▼
Dependencies (backend/dependencies/*) ← auth, authorization, pagination, DB session
        ▼
Services (backend/services/*)       ← all business logic lives here
        ▼
Repositories (backend/repositories/*) ← data access only
        ▼
PostgreSQL 17  +  Qdrant (vector DB)  +  Ollama (LLM)
```

Each layer has one job:

- **API routers** translate HTTP into service calls and services results back
  into HTTP. They do validation with Pydantic schemas and nothing else.
- **Dependencies** provide cross-cutting concerns: the current user, the
  database session, permission checks, and pagination limits.
- **Services** contain the actual logic (authentication, document processing,
  retrieval, generation, auditing). This is where almost all the interesting
  code is.
- **Repositories** are thin data-access helpers over SQLAlchemy and the Qdrant
  client. They do not contain business rules.

Keeping logic in services (not in routers or repositories) is what makes the
code testable: services can be unit-tested with a fake database session and a
fake LLM client, without any network.

## The main modules

| Module | Location | Responsibility |
|--------|----------|----------------|
| Config | `backend/core/config.py` | Loads settings from env vars / `.env`; validates production safety at startup |
| Security | `backend/core/security.py` | Argon2 password hashing, JWT create/decode, refresh-token hashing |
| Middleware | `backend/core/middleware.py` | Request ID generation + structured request logging |
| Exceptions | `backend/core/exceptions.py`, `exception_handlers.py` | Typed domain errors mapped to HTTP status codes |
| Auth | `backend/services/auth_service.py`, `refresh_token_service.py`, `login_throttle.py` | Register/login/refresh/logout, brute-force throttling |
| Organizations | `backend/services/organization_service.py`, `organization_membership_service.py` | Tenant creation and membership/role management |
| Documents | `backend/services/document_service.py`, `document_extraction.py`, `document_chunking.py`, `document_processing_service.py`, `document_indexing_service.py` | Upload → validate → extract → chunk → embed → index |
| Retrieval | `backend/services/retrieval_service.py`, `bm25_service.py`, `retrievers.py`, `hybrid_retrieval_service.py` | Dense + lexical search, RRF fusion, cross-encoder reranking |
| Generation | `backend/services/generation_service.py`, `rag_service.py` | Grounded answers, citations, refusal, SSE streaming |
| LLM clients | `backend/services/llm/*` | Provider abstraction (Ollama, OpenAI-compatible) |
| Embeddings | `backend/services/embedding_service.py` | BGE-M3 sentence embeddings |
| Audit | `backend/services/audit_service.py` | Append-only audit log with an allowlisted detail set |
| Evaluation | `backend/evaluation/*` | Offline + live retrieval and answer-quality benchmarks |

## Data stores

NEXORA uses three external systems, each for what it is best at:

1. **PostgreSQL 17** — the source of truth. Users, organizations, memberships,
   document metadata, chunk text, refresh tokens, and audit logs. Seven tables
   (see [multi-tenancy.md](multi-tenancy.md) and the schema notes below).
2. **Qdrant** — the vector database. Holds one 1024-dimensional embedding per
   document chunk for fast similarity search. Each point carries
   `organization_id`, `document_id`, `chunk_id`, and `chunk_index` as payload,
   and its point id equals the Postgres chunk id.
3. **Ollama** — the local LLM runtime (model `qwen3:8b`). Generates the final
   answer text from the retrieved chunks. An OpenAI-compatible provider is also
   supported but is optional.

Postgres is authoritative: after Qdrant returns candidate chunk ids, the
retrieval service re-fetches those chunks **from Postgres, filtered by the same
organization**. A vector can therefore never leak a chunk to a tenant that does
not own the underlying row.

## The two main flows

### Ingestion (upload → searchable)

1. Client uploads a file (PDF or DOCX) to an organization.
2. The file is validated (size, content type, **magic bytes**), stored on disk
   under a per-organization path, and a `documents` row is created with status
   `pending`.
3. A **FastAPI BackgroundTask** picks it up: status → `processing`, text is
   extracted (page-aware), split into overlapping chunks with page provenance,
   chunks are saved to Postgres, embedded with BGE-M3, and upserted to Qdrant.
4. On success status → `ready` (with page/word/character counts). On failure
   status → `failed` with a short, non-leaky `failure_reason`.

The BM25 lexical index is built lazily per organization and invalidated when
chunks change.

### Query (question → grounded answer)

1. Client posts a question to an organization (optionally restricted to a list
   of `document_ids`).
2. **Hybrid retrieval** runs: dense (Qdrant) + lexical (BM25) → **RRF** fusion →
   **cross-encoder rerank** → drop chunks below a relevance threshold → keep the
   top `RETRIEVAL_TOP_K` (default 2).
3. If **zero** chunks survive, the system returns a canned "documents do not
   contain enough information" refusal **without calling the LLM**.
4. Otherwise the chunks are numbered and placed in a grounded system prompt; the
   LLM answers with inline `[n]` citations. Citation markers that do not map to
   a real source are stripped.
5. The response includes the answer plus `sources` (each with a 1-based
   `citation_index`, document name, chunk index, page range, and score).

A streaming variant (`/query/stream`) sends Server-Sent Events: `token` deltas
as they arrive, then a terminal `done` event with the full answer, sources, and
timing (`ttft_ms`, `total_ms`), or an `error` event.

## Dependency injection and singletons

Expensive objects (the embedding model, the Qdrant client, the LLM client) are
created **lazily** and cached per process with `@lru_cache(maxsize=1)`:
`get_embedding_service`, `get_qdrant_repository`, `get_llm_client`. This means
the API can start and answer `/health` without loading model weights or
touching Qdrant, and heavy resources are built once on first use. Because the
cache is per-process, running multiple replicas is safe (each has its own).

## Request tracking

`RequestObservabilityMiddleware` assigns every request an `X-Request-ID` (a
client-supplied id is accepted only if it is ≤128 chars and matches
`^[A-Za-z0-9._-]+$`; otherwise a UUID is generated). The id is stored in a
`ContextVar` so the audit service can attach it to audit rows without threading
it through every function call. Request logging records **only** request id,
method, path, status code, and duration — never headers, bodies, or query
strings.

## What NEXORA deliberately does not use

- No LangChain core / LangGraph (only `langchain-text-splitters` for chunking
  and `langchain-huggingface` for embeddings).
- No Redis, Celery, or external task queue (background work uses FastAPI's
  built-in `BackgroundTasks`; the login throttle is in-process).
- No Kubernetes or microservice split.
- No OCR, scanned-image, or PDF-table extraction (see
  [document-ingestion.md](document-ingestion.md)).

These are conscious scope decisions, not gaps: the brief for this project is to
keep NEXORA a modular monolith unless a real technical requirement says
otherwise.
