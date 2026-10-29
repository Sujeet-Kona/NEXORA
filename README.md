# NEXORA

**Production-oriented multi-tenant Enterprise RAG platform** built as a FastAPI
modular monolith.

NEXORA lets organizations upload PDF/DOCX documents and ask questions against
their own data. The system retrieves evidence first, generates grounded answers
with source citations, and refuses when the available evidence is insufficient.

> **Evaluation note:** the current live retrieval benchmark uses 16 documents,
> 220 chunks, and 60 evaluation questions. The results below are benchmark
> measurements, not production SLAs or universal accuracy claims.

---

## 1. What it does

NEXORA combines:

- multi-tenant organizations and RBAC
- JWT authentication with rotating/revocable refresh tokens
- Argon2 password hashing and login throttling
- PDF/DOCX ingestion with validation and page provenance
- dense vector retrieval with Qdrant
- BM25 lexical retrieval
- Reciprocal Rank Fusion (RRF)
- cross-encoder reranking and relevance filtering
- grounded generation with citations
- deterministic no-context refusal without an LLM call
- Server-Sent Events (SSE) streaming
- document versioning and lifecycle recovery
- append-only audit logging
- automated tests and CI
- live/offline evaluation harnesses with cleanup verification
- Dockerized deployment configuration

The core RAG flow is implemented directly in Python rather than relying on
LangChain/LangGraph as the application orchestration layer.

## 2. Architecture

```text
Client
  ↓
FastAPI API
  ↓
Authentication / RBAC / tenant identification
  ↓
Services
  ↓
Repositories
  ├── PostgreSQL  ← source of truth
  ├── Qdrant      ← vector index
  └── Ollama      ← local LLM
```

### Ingestion

```text
Upload
  ↓
Validation
  ↓
Document storage
  ↓
Extraction
  ↓
Chunking + page provenance
  ↓
BGE-M3 embeddings
  ↓
Qdrant indexing
  ↓
Document READY
```

### Query

```text
Question
  ↓
Validation + authorization
  ↓
BM25 ─────────┐
              ├─→ RRF → cross-encoder → relevance filter
Dense/Qdrant ─┘                         ↓
                                  top-k context
                                         ↓
                                      grounded LLM
                                         ↓
                                  answer + citations
```

If no chunk survives the relevance threshold, NEXORA returns a deterministic
refusal without calling the LLM.

## 3. Technology stack

| Concern | Technology |
|---|---|
| API | FastAPI, Starlette, Uvicorn |
| Validation/config | Pydantic v2, pydantic-settings |
| Database | PostgreSQL 17, SQLAlchemy 2.0, Alembic |
| Vector store | Qdrant |
| Embeddings | `BAAI/bge-m3`, sentence-transformers |
| Lexical retrieval | `rank-bm25` / BM25Okapi |
| Reranker | `cross-encoder/ms-marco-MiniLM-L-6-v2` |
| Chunking | `langchain-text-splitters` |
| LLM | Ollama (`qwen3:8b` default) |
| Authentication | PyJWT, Argon2 via pwdlib |
| Documents | PyMuPDF, python-docx |
| Testing | pytest |
| Deployment | Docker / Docker Compose |
| CI | GitHub Actions |

There is no LangChain core, LangGraph, Redis, or Celery dependency in the core
application flow.

## 4. Security and isolation

NEXORA treats tenant isolation as a correctness and security requirement, not
just an application convention.

- organization-scoped API and service operations
- organization filtering in Postgres and Qdrant
- Postgres re-check of returned vector hits before their text is exposed
- owner/admin/member authorization model
- Argon2 password hashing
- JWT expiry enforcement
- rotating and revocable refresh tokens
- JTI denylisting
- login throttling
- upload size, content-type, and magic-byte validation
- guarded local file storage
- parameterized/ORM database access
- static error responses that avoid internal leakage
- request IDs without logging request bodies or secrets
- append-only audit logging with an allowlisted detail set
- production configuration validation

## 5. Document processing

Supported document types:

- PDF
- DOCX, including DOCX tables

Not currently claimed:

- OCR for scanned/image-only PDFs
- image understanding
- PDF table extraction
- arbitrary document formats such as XLSX/PPTX/CSV/HTML

Chunking preserves page provenance for PDFs. Document processing includes
lifecycle states and recovery handling for stale `PROCESSING` documents and
failed-document retry flows.

## 6. Retrieval

NEXORA uses two first-stage retrievers:

1. **Dense retrieval** — semantic similarity using BGE-M3 embeddings in Qdrant.
2. **BM25** — lexical matching for exact terms, names, identifiers, and policy
   language.

The ranked results are combined using **Reciprocal Rank Fusion (RRF)**. A small
candidate set is then evaluated by a cross-encoder reranker and filtered by a
relevance threshold before context is sent to the LLM.

The system does not assume that reranking must improve the benchmark. Its effect
is measured and reported honestly.

## 7. Current evaluation

The current live benchmark was run through the real production ingestion and
retrieval path using:

- **16 documents**
- **220 chunks**
- **60 evaluation questions**

| Configuration | Recall@1 | Recall@5 | Recall@10 | Precision@10 | MRR |
|---|---:|---:|---:|---:|---:|
| BM25 | **66.67%** | 86.67% | 95.00% | 9.50% | **0.7483** |
| Dense | 63.33% | 86.67% | **100.00%** | 10.00% | 0.7334 |
| Hybrid RRF | 63.33% | **93.33%** | **100.00%** | 10.00% | 0.7481 |
| Hybrid + reranker | 63.33% | **93.33%** | **100.00%** | 10.00% | 0.7440 |
| Hybrid Full | 63.33% | 83.33% | 85.00% | 8.50% | 0.7056 |

### What these numbers mean

- **66.67% is the best Recall@1**, not 93.33%.
- **93.33% is Recall@5** for Hybrid RRF and Hybrid + reranker.
- **100% Recall@10** means the relevant ground-truth evidence was present in
  the top ten for those configurations.
- The cross-encoder **did not improve the current benchmark**: its MRR is
  0.7440 versus 0.7481 for RRF.

This is a controlled engineering benchmark. It is not a claim that NEXORA is
93.33% accurate, nor that the system will achieve these numbers on arbitrary
enterprise data.

### Cleanup proof

The completed live benchmark left:

- 0 documents
- 0 chunks
- 0 organizations
- 0 users
- 0 Qdrant points

The benchmark therefore cleans up the temporary evaluation data it creates.

Detailed results: [`docs/evaluation.md`](docs/evaluation.md).

## 8. Grounding and citations

NEXORA uses two grounding mechanisms:

1. **Deterministic refusal:** no relevant chunk means no LLM call.
2. **Grounded generation:** the model is instructed to answer from retrieved
   context and decline when the context is insufficient.

Retrieved chunks are numbered and returned as structured sources. Invalid
citation markers are removed after generation so citations map to actual
retrieved sources.

## 9. Reliability and lifecycle handling

Document processing includes safeguards for concurrent lifecycle operations:

- row locking around processing claims
- protection against replacement/deletion while processing
- stale `PROCESSING` recovery
- explicit FAILED → PENDING retry semantics
- processing lease refresh before external indexing
- locking before Qdrant mutation for replacement/deletion
- regression tests for lifecycle races

Qdrant is treated as an index rather than the source of truth. Normal retrieval
only exposes chunks belonging to READY documents.

## 10. Evaluation commands

Offline BM25 benchmark:

```bash
.venv/bin/python -m backend.evaluation.benchmark
```

Current live retrieval benchmark:

```bash
HF_HUB_OFFLINE=1 .venv/bin/python -u -m backend.evaluation.benchmark --live
```

End-to-end answer benchmark:

```bash
.venv/bin/python -m backend.evaluation.answer_benchmark
```

The live retrieval benchmark requires the local PostgreSQL, Qdrant, embedding,
and reranker runtime. It creates temporary benchmark data and removes it after
the run.

## 11. Local development

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
docker compose up -d
ollama pull qwen3:8b
cp .env.example .env
alembic upgrade head
python -m uvicorn backend.main:app --reload
```

API: `http://127.0.0.1:8000`

Swagger/OpenAPI: `http://127.0.0.1:8000/docs`

Health: `http://127.0.0.1:8000/health`

## 12. Production scope

The repository contains a non-root multi-stage Docker image and production
Compose configuration with PostgreSQL and Qdrant.

A real larger deployment would additionally need operational decisions around
persistent/shared object storage, distributed rate limiting, durable ingestion,
TLS, backups, observability, load testing, and capacity planning.

Those are intentionally not represented as implemented features unless they are
actually present in the repository.

## 13. Honest limitations

NEXORA is a **production-oriented engineering project**, not a claim of a fully
managed production SaaS system.

Known limitations include:

- controlled and relatively small evaluation corpus
- local disk storage implementation
- process-local login throttling
- FastAPI BackgroundTasks rather than a durable distributed queue
- no OCR/image-only document understanding
- no throughput/concurrency benchmark
- no universal answer-quality or human-helpfulness score
- local LLM latency depends heavily on hardware

The project deliberately favors explicit, testable engineering over adding
infrastructure that is not justified by the current requirements.

## 14. Project status

**NEXORA — final engineering/evaluation baseline complete.**

The core application, security hardening, lifecycle recovery, automated testing,
CI, evaluation harnesses, live benchmark, cleanup verification, and documentation
are in place. The retrieval benchmark is frozen as a measured baseline rather
than being tuned solely for a better headline number.

See [`docs/`](docs/) for architecture, retrieval, security, evaluation,
deployment, configuration, and interview notes.
