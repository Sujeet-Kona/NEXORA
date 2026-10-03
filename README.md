# NEXORA

Secure, multi-tenant **Enterprise RAG** platform: upload your documents, ask
questions in plain English, and get **grounded, cited answers** — never
hallucinations. Built as a FastAPI modular monolith.

> This README describes what NEXORA **actually does today**, verified by tests
> and benchmarks. Deeper detail lives in [`docs/`](docs/). Numbers quoted here
> were measured on **2026-09-28** on a local machine and are **indicative**, not
> a production SLA.

---

## 1. What is NEXORA?

NEXORA is a backend platform that lets multiple organizations (tenants) store
their own documents and question them with an AI assistant. It uses **RAG**
(Retrieval-Augmented Generation): instead of letting a language model answer from
memory, NEXORA first **retrieves** the relevant passages from *your* documents and
then asks the model to answer **using only those passages**, with citations back
to the source. If the documents don't contain the answer, NEXORA says so rather
than making something up.

All application endpoints are versioned under `/api/v1`; `/health` is the only
unversioned endpoint.

## 2. Problem it solves

General-purpose LLMs don't know your private policies, and they confidently invent
answers when they don't know something. Enterprises need a Q&A assistant that:

- answers **only** from approved internal documents,
- **cites** the exact source (document, chunk, page) for every answer,
- **refuses** when the documents don't support an answer,
- keeps each tenant's data **strictly isolated**,
- is **secure** (hashed passwords, JWT auth, RBAC, audit log), and
- can run **entirely on your own infrastructure** (local LLM, no data leaves).

NEXORA addresses all of these.

## 3. Main features

- Multi-tenant organizations with owner/admin/member roles.
- JWT authentication (access + rotating refresh tokens), Argon2 passwords,
  brute-force login throttling.
- Document upload (PDF, DOCX) with size/type/magic-byte validation.
- Page-aware extraction, overlapping chunking with page provenance.
- Hybrid retrieval: dense vectors (Qdrant) + BM25, fused with RRF, reranked by a
  cross-encoder.
- Grounded answers with inline citations and two independent refusal mechanisms.
- SSE streaming with time-to-first-token reporting.
- Append-only audit log with a secret-safe detail allowlist.
- Document versioning (re-index on replace) and tenant-scoped deletion.
- Offline + live evaluation benchmarks with cleanup proofs.
- Multi-stage non-root Docker image, production compose, and CI.

## 4. Architecture

A **modular monolith** with clean layers:

```
Client → FastAPI → Auth/Authz (dependencies) → Services → Repositories → PostgreSQL
                                                              ↘ Qdrant (vectors)
                                                              ↘ Ollama (LLM)
```

- **API routers** (`backend/api/v1/`) — HTTP in/out, Pydantic validation only.
- **Dependencies** (`backend/dependencies/`) — current user, DB session,
  permission checks, pagination.
- **Services** (`backend/services/`) — all business logic.
- **Repositories** (`backend/repositories/`) — thin data access (SQLAlchemy,
  Qdrant client).
- **Stores** — PostgreSQL (source of truth), Qdrant (vector index), Ollama (LLM).

Expensive clients (embeddings, Qdrant, LLM) are built lazily and cached
per-process (`@lru_cache`), so the API starts fast and scales safely across
replicas. Full explanation: [docs/architecture.md](docs/architecture.md).

## 5. Technology stack

| Concern | Choice |
|---------|--------|
| Web framework | FastAPI (Starlette), uvicorn |
| Validation/settings | Pydantic v2 + pydantic-settings |
| ORM / migrations | SQLAlchemy 2.0, Alembic (PostgreSQL-only, single head) |
| Database | PostgreSQL 17 (psycopg 3) |
| Vector store | Qdrant (qdrant-client), 1024-dim cosine |
| Embeddings | `BAAI/bge-m3` via sentence-transformers (normalized) |
| Lexical search | `rank-bm25` (BM25Okapi) |
| Reranker | `cross-encoder/ms-marco-MiniLM-L-6-v2` |
| Chunking | `langchain-text-splitters` (RecursiveCharacterTextSplitter) |
| LLM | Ollama `qwen3:8b` (default); OpenAI-compatible optional |
| Auth | PyJWT (HS256), `pwdlib[argon2]` |
| PDF / DOCX | `pymupdf` / `python-docx` |
| Tests | pytest |

All dependencies are pinned in `requirements.txt`. **No** LangChain core,
LangGraph, Redis, or Celery.

## 6. RAG pipeline

```
question → hybrid retrieval → 0..N chunks
   ├─ 0 chunks → canned refusal (NO LLM call)
   └─ ≥1 chunk → number [1..N] → grounded prompt → LLM → strip invalid citations → answer + sources
```

Detail: [docs/rag-pipeline.md](docs/rag-pipeline.md).

## 7. Authentication

JWT bearer tokens. Passwords hashed with **Argon2**. Login is **constant-time**
(always one Argon2 verify, using a dummy hash for unknown emails) and returns a
uniform 401, so it can't be used to enumerate accounts. Access tokens require an
`exp` claim (default 30 min). Refresh tokens are random 32-byte strings stored as
**SHA-256 hashes**, **rotated** on use, and revocable; logout revokes. A
per-email **login throttle** returns 429 + `Retry-After` after 5 failures.
Detail: [docs/authentication.md](docs/authentication.md).

## 8. Multi-tenancy

Two independent role levels: **platform** (`admin`/`member`) and
**organization** (`owner`/`admin`/`member`). Seven tables (users, refresh_tokens,
organizations, organization_memberships, documents, document_chunks, audit_logs).
Tenant isolation is enforced at **four layers** (API, service, Postgres, Qdrant)
plus a **post-query re-check**: every Qdrant hit is re-fetched from Postgres
filtered by organization, so a stray vector can never leak another tenant's text.
Detail: [docs/multi-tenancy.md](docs/multi-tenancy.md).

## 9. Document ingestion

Upload → validate → store → background-process → searchable.

- **Supported formats: PDF and DOCX only.** PDF is extracted per page (pymupdf);
  DOCX includes paragraphs **and tables** (python-docx).
- **Not supported:** OCR, scanned/image-only documents, images, PDF tables, and
  any other format (txt, md, xlsx, pptx, csv, html).
- Validation: non-empty filename/content, ≤ `MAX_UPLOAD_SIZE_BYTES` (10 MiB),
  content-type allowlist, and **magic-byte** check (`%PDF-` / `PK`).
- Chunking: size 3000, overlap 400, with page provenance.
- Processing runs in a FastAPI **BackgroundTask**: extract → chunk → embed
  (BGE-M3) → upsert to Qdrant → mark `ready` (or `failed` with a generic reason).

Detail: [docs/document-ingestion.md](docs/document-ingestion.md).

## 10. Retrieval

Hybrid retrieval combines two searches:

- **Dense** — embed the question (BGE-M3), find nearest chunk vectors in Qdrant
  (semantic match).
- **Lexical (BM25)** — keyword/term match (catches exact terms, IDs, names).

Candidates are fused (RRF), reranked (cross-encoder), filtered by a relevance
threshold, and truncated to `RETRIEVAL_TOP_K` (default 2). An optional
`document_ids` filter is applied at every stage.
Detail: [docs/retrieval.md](docs/retrieval.md).

## 11. RRF (Reciprocal Rank Fusion)

RRF merges the dense and BM25 ranked lists by **rank**, not raw score: each chunk
gets `1 / (k + rank)` summed across the lists it appears in, with `k = 60`. A
chunk ranked high by **both** retrievers rises to the top. Because it uses ranks,
RRF doesn't care that vector cosine scores and BM25 scores are on different
scales. Measured effect: Recall@1 0.6333 → 0.6500, MRR 0.9611 → 0.9778.

## 12. Reranking

The fused candidates are rescored by a **cross-encoder**
(`cross-encoder/ms-marco-MiniLM-L-6-v2`), which reads the question and each chunk
**together** and outputs a relevance score (through a sigmoid). This is more
accurate than either first-stage retriever but slower, so it's applied only to the
small fused set. Chunks below `RETRIEVAL_MIN_RELEVANCE` (default 0.5) are
dropped. Measured effect: Recall@1 → 0.6667, **MRR → 1.0000** (a relevant chunk
at rank 1 for every case).

## 13. Grounding

Two independent refusal mechanisms keep answers grounded:

1. **Deterministic (no LLM):** if zero chunks clear the relevance threshold,
   return the canned "The available documents do not contain enough information
   to answer this question." — the model is never called.
2. **Model judgement:** the grounded system prompt instructs the model to answer
   only from context and to say so if the context is insufficient.

Measured refusal rate on out-of-corpus questions: **3/3**.

## 14. Citations

Retrieved chunks are numbered `[1]..[N]` and the model is instructed to cite
inline. After generation, `_strip_invalid_citations` removes any `[n]` marker
whose number falls outside `1..N`, so citations always map to a real source. Each
returned source carries a 1-based `citation_index`, `document_name`,
`chunk_index`, `page_start`/`page_end`, and `score`. Measured citation accuracy:
**30/30**.

## 15. Streaming

`POST /api/v1/organizations/{id}/query/stream` returns Server-Sent Events
(`text/event-stream`, `Cache-Control: no-cache`, `X-Accel-Buffering: no`).
Retrieval runs eagerly (so retrieval errors surface as normal HTTP errors), then
the endpoint emits `token` deltas, followed by a terminal `done` event carrying
the full `answer`, `sources`, and `timing` (`ttft_ms`, `total_ms`) — or an `error`
event. The canned-refusal path emits `done` immediately (no LLM call).

## 16. Evaluation

Two harnesses in `backend/evaluation/`, both producing real measurements with a
zero-leftover cleanup proof:

- `benchmark.py` — retrieval quality (offline BM25 comparison + `--live`
  dense/BM25/hybrid through the real pipeline).
- `answer_benchmark.py` — end-to-end fact/citation/refusal accuracy + latency.

**Historical retrieval benchmark (30 positive + 3 negative cases, 10 docs, 2026-09-28):**

| config | Recall@1 | Recall@10 | Prec@10 | MRR |
|--------|----------|-----------|---------|-----|
| bm25 | 0.6333 | 1.0000 | 0.1667 | 0.9611 |
| dense | 0.6333 | 1.0000 | 0.1667 | 0.9611 |
| hybrid_rrf | 0.6500 | 1.0000 | 0.1667 | 0.9778 |
| **hybrid_full** | **0.6667** | 0.9833 | 0.1633 | **1.0000** |

**Answer quality:** fact **30/30**, citation **30/30**, refusal **3/3** (both
top_k=2 and top_k=10). Detail: [docs/evaluation.md](docs/evaluation.md).

## 17. Performance

Single-run local measurements (Apple Silicon, Ollama `qwen3:8b`,
`OLLAMA_THINK=false`):

| config | total mean | total median | total p95 | total max | gen mean |
|--------|-----------|--------------|-----------|-----------|----------|
| top_k=2 (default) | 10.47s | 9.37s | 18.79s | 30.99s | 9.04s |
| top_k=10 | 6.56s | 4.22s | 16.99s | 26.00s | 5.88s |

Latency is dominated by local LLM inference. **Not measured:** TTFT
distribution, per-stage latency, throughput/concurrency, token counts, dollar
cost. These are indicative, **not** production SLAs, and top_k=10 is **not**
"faster" (single-run noise). Detail: [docs/performance.md](docs/performance.md).

## 18. Security

Argon2 hashing; constant-time login; exp-required JWT; SHA-256 refresh hashes
with rotation/revocation; login throttle → 429; two-level RBAC; four-layer tenant
isolation + Postgres re-check; upload size/type/magic-byte validation;
path-traversal-guarded storage; ORM/parameterized queries (no SQLi); typed errors
→ static messages (no internal leakage); request-id logging that never records
bodies/headers/secrets; append-only audit log with an allowlisted detail set;
production fail-fast config validation; `.env` untracked and no tracked secrets.
Detail: [docs/security.md](docs/security.md).

## 19. Docker

- `Dockerfile` — multi-stage, slim, **non-root** image; uvicorn on 8000;
  healthcheck on `/health`.
- `docker-entrypoint.sh` — waits for Postgres, runs `alembic upgrade head`
  (unless `RUN_MIGRATIONS=false`), then execs the CMD. Logs only the exception
  class on DB failure (never the URL).
- `docker-compose.prod.yml` — API + `postgres:17` + `qdrant:v1.19.1`, named
  volumes, only the API port published, and **required** `POSTGRES_PASSWORD` /
  `JWT_SECRET_KEY` (`:?` guards).
- `docker-compose.yml` — dev-only Postgres + Qdrant.

**Verification status (2026-09-28):** `docker compose -f docker-compose.prod.yml
config -q` **passes** offline. The image **build** and a live compose **boot**
were **not verified** because the Docker daemon would not start on the audit
machine. Exact commands to finish verification:
[docs/deployment.md](docs/deployment.md).

## 20. CI/CD

`.github/workflows/ci.yml` runs on push to `main` and on PRs: a **Postgres-only**
service container (tests use fakes for Qdrant/Ollama), then `alembic upgrade
head`, `python -m compileall -q backend`, and `pytest -q`. `ENVIRONMENT` is not
set in CI, so production fail-fast validation isn't triggered.

## 21. Local setup

```bash
python -m venv .venv && source .venv/bin/activate
python -m pip install -r requirements-dev.txt   # runtime + pytest (prod image uses requirements.txt)
docker compose up -d                      # Postgres + Qdrant
ollama pull qwen3:8b                       # LLM
cp .env.example .env                       # set DATABASE_URL + JWT_SECRET_KEY
alembic upgrade head
python -m uvicorn backend.main:app --reload
```

API: http://127.0.0.1:8000 · Docs: http://127.0.0.1:8000/docs · Health:
http://127.0.0.1:8000/health. Full guide: [docs/setup.md](docs/setup.md).

## 22. Production setup

```bash
POSTGRES_PASSWORD='...' JWT_SECRET_KEY='...' \
  docker compose -f docker-compose.prod.yml up -d --build
```

Set `ENVIRONMENT=production` (enables fail-fast validation), explicit
`CORS_ORIGINS` (no wildcard), a strong `JWT_SECRET_KEY` (≥32 random chars), and
fully configure the active LLM provider. Provision persistent volumes and
Postgres backups; put TLS in front of the API. See
[docs/deployment.md](docs/deployment.md) and the conditions in
[docs/deployment-readiness.md](docs/deployment-readiness.md).

## 23. Environment variables

Full contract in `.env.example` and [docs/configuration.md](docs/configuration.md).
Key variables:

| Variable | Default | Notes |
|----------|---------|-------|
| `ENVIRONMENT` | `development` | `production` enables fail-fast validation |
| `DATABASE_URL` | required | `postgresql+psycopg://...` |
| `JWT_SECRET_KEY` | required | ≥32 chars in production |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `30` | |
| `LOGIN_MAX_FAILED_ATTEMPTS` / `LOGIN_LOCKOUT_SECONDS` | `5` / `300` | |
| `CORS_ORIGINS` | empty | empty disables CORS; wildcard rejected in prod |
| `STORAGE_PATH` / `MAX_UPLOAD_SIZE_BYTES` | `storage` / `10485760` | |
| `QDRANT_URL` / `QDRANT_COLLECTION` | `http://localhost:6333` / `nexora_document_chunks` | |
| `EMBEDDING_MODEL` / `EMBEDDING_DIMENSION` | `BAAI/bge-m3` / `1024` | |
| `RETRIEVAL_TOP_K` / `_DENSE_TOP_K` / `_LEXICAL_TOP_K` / `_RERANK_TOP_K` | `2` / `10` / `10` / `8` | all ≥1 |
| `RETRIEVAL_MIN_RELEVANCE` | `0.5` | grounding threshold |
| `LLM_PROVIDER` | `ollama` | `ollama` or `openai` |
| `OLLAMA_MODEL` / `OLLAMA_THINK` | `qwen3:8b` / `false` | model required in prod |
| `OPENAI_API_KEY` / `OPENAI_MODEL` | empty | required in prod if provider=openai |

## 24. API examples

Register and login:

```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H 'content-type: application/json' \
  -d '{"email":"alice@example.com","full_name":"Alice","password":"supersecret1"}'

curl -X POST http://localhost:8000/api/v1/auth/login \
  -H 'content-type: application/json' \
  -d '{"email":"alice@example.com","password":"supersecret1"}'
# → {"access_token":"...","refresh_token":"...","token_type":"bearer"}
```

Create an organization, upload a document, and query it:

```bash
TOKEN="<access_token>"

curl -X POST http://localhost:8000/api/v1/organizations \
  -H "authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"name":"Acme"}'

curl -X POST http://localhost:8000/api/v1/organizations/1/documents/upload \
  -H "authorization: Bearer $TOKEN" -F "file=@leave_policy.docx"

curl -X POST http://localhost:8000/api/v1/organizations/1/query \
  -H "authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"question":"How many days of annual leave do employees receive?"}'
# → {"answer":"Employees receive 20 days of annual leave per year [1].",
#    "sources":[{"citation_index":1,"document_name":"leave_policy.docx", ...}]}
```

Full reference: [docs/api.md](docs/api.md) (or `/docs` when running).

## 25. Project structure

```
NEXORA/
├── backend/
│   ├── main.py                 # FastAPI app, middleware, exception handlers, /health
│   ├── api/
│   │   ├── router.py           # aggregates v1 routers
│   │   └── v1/                 # auth, users, organizations, documents, rag, audit
│   ├── core/                   # config, security, middleware, logging,
│   │                           #   request_context, exceptions, exception_handlers
│   ├── db/                     # database.py (engine/session), models.py (7 tables)
│   ├── dependencies/           # auth, authorization, organization_authorization,
│   │                           #   database, pagination, rag
│   ├── schemas/                # Pydantic request/response models
│   ├── repositories/           # data access: user, organization, document,
│   │                           #   document_chunk, refresh_token, audit, qdrant
│   ├── services/               # ALL business logic:
│   │   ├── auth_service, refresh_token_service, login_throttle
│   │   ├── organization_service, organization_membership_service
│   │   ├── document_service, document_extraction, document_chunking,
│   │   │   document_processing_service, document_processing_worker,
│   │   │   document_indexing_service, storage
│   │   ├── embedding_service, bm25_service, retrieval_service, retrievers,
│   │   │   hybrid_retrieval_service
│   │   ├── generation_service, rag_service
│   │   ├── audit_service, user_service
│   │   └── llm/                # base (protocol), provider, ollama_client, openai_client
│   └── evaluation/             # dataset, metrics, benchmark, answer_benchmark
├── alembic/                    # migrations (versions/), env.py; alembic.ini
├── tests/                      # unit + API tests; tests/integration (Qdrant)
├── scripts/                    # manual check scripts (ollama/openai/real-rag)
├── docs/                       # this documentation set
├── benchmark-data/             # 10 .docx + 6 research-paper PDFs used by the benchmarks
├── Dockerfile, docker-entrypoint.sh, .dockerignore
├── docker-compose.yml (dev), docker-compose.prod.yml
├── .github/workflows/ci.yml
├── requirements.txt, pytest.ini, .env.example
└── README.md
```

**How it connects:** `main.py` mounts the `api/v1` routers behind
`dependencies/` (auth, authorization, DB session, pagination). Routers call
`services/`, which contain the logic and talk to `repositories/` (Postgres via
SQLAlchemy, vectors via the Qdrant repository). `core/` provides cross-cutting
concerns (config, security, middleware, exceptions). `evaluation/` reuses the
same services to benchmark the real pipeline.

## 26. Limitations

- **Formats:** PDF and DOCX only. No OCR, images, PDF tables, or other formats.
- **Login throttle is per-process** — not a global limit across replicas.
- **Local-disk upload storage only** — multi-replica needs shared/object storage.
- **Background ingestion** uses FastAPI `BackgroundTasks`, not a durable queue;
  in-flight work is lost on process death (document → `failed`, retriable).
- **Evaluation history.** The latest measured live benchmark is the 2026-09-28 10-doc run; the current corpus is larger (16 docs / 60 positive + 6 negative cases) and must be re-measured before new live metrics are quoted.
- **Not measured:** TTFT distribution, per-stage latency, throughput, token
  counts, dollar cost.
- **No dependency CVE scanning** in CI (deps are pinned).
- **Docker production stack** not verified in this pass (daemon unavailable).

## 27. Future improvements

Only as real requirements justify them (NEXORA stays a modular monolith):

- Shared login-throttle store and API-wide rate limiting for multi-replica.
- Object storage backend for uploads.
- Durable ingestion queue (resume/retry on worker failure).
- Dependency vulnerability scanning (`pip-audit`/Dependabot) in CI.
- Metrics/tracing (Prometheus/OpenTelemetry) and aggregated TTFT/throughput
  measurement under load.
- Larger, noisier evaluation corpus and human-rated answer quality.
- Optional OCR / image / PDF-table extraction (clearly gated, since it does not
  exist today).

---

## Running the tests

```bash
pytest -q                                   # 564 passed, 3 skipped (current verified suite; in-memory SQLite; no Postgres/Qdrant/Ollama needed)
python -m compileall backend                # compiles clean
```

The 3 skips are `tests/test_migrations.py`, which require a real PostgreSQL via
`TEST_DATABASE_URL` (name must contain `test`):

```bash
TEST_DATABASE_URL=postgresql+psycopg://nexora:nexora@localhost:5432/nexora_test \
  pytest -q tests/test_migrations.py
```

## Documentation

[`docs/`](docs/): architecture · setup · configuration · authentication ·
multi-tenancy · document-ingestion · retrieval · rag-pipeline · evaluation ·
performance · deployment · security · api · troubleshooting · interview-notes ·
deployment-readiness.

## Deployment readiness

**READY WITH CONDITIONS** — the application, security, tests, migrations,
retrieval, and RAG pipeline are verified; the Docker production stack still needs
a live boot check on a machine with a working daemon, and a few scale-out items
are tracked as pre-production work. Full assessment:
[docs/deployment-readiness.md](docs/deployment-readiness.md).
