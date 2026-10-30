# Deployment Readiness

**Assessment date:** 2026-10-30  
**Scope:** current NEXORA codebase after final hardening, gap closure, evaluation
updates, and documentation cleanup.

## 1. Executive status

### Application baseline: READY FOR RESUME / PORTFOLIO USE

The application has a verified engineering baseline with automated tests,
PostgreSQL migrations, tenant-scoped authorization, retrieval evaluation,
security controls, document lifecycle recovery, and CI checks.

### Public production deployment: NOT CLAIMED

NEXORA is intentionally documented as **production-oriented**, not as a fully
operational production SaaS. A real deployment would still require operational
infrastructure such as TLS/secrets management, backups and disaster recovery,
shared storage for multiple replicas, durable background jobs, centralized
observability, capacity testing, and production model serving.

That distinction is deliberate. The repository does not claim traffic,
availability, throughput, or scale that has not been measured.

## 2. Current verification evidence

### Automated test and CI baseline

The final hardening/gap-closure baseline reached:

- **572 tests passed**
- **2 tests skipped**
- 0 test failures
- dependency security audit included in CI via `pip-audit`
- backend byte-compilation checked in CI
- Alembic migrations executed in CI against PostgreSQL 17

CI runs the test stack through GitHub Actions. The live retrieval benchmark is
not part of CI because it requires heavyweight embedding/reranker models and
Qdrant.

### Live retrieval evaluation

The current live benchmark uses the production document-processing path and
reports:

- 16 benchmark documents
- 220 processed chunks
- 60 evaluation questions
- BM25, dense retrieval, RRF, cross-encoder reranking, and full hybrid variants
- cleanup verification after the run

Current headline result:

| Configuration | Recall@1 | Recall@5 | Recall@10 | Precision@10 | MRR |
|---|---:|---:|---:|---:|---:|
| BM25 | **0.6667** | 0.8667 | 0.9500 | 0.0950 | **0.7483** |
| Dense | 0.6333 | 0.8667 | **1.0000** | 0.1000 | 0.7334 |
| Hybrid RRF | 0.6333 | **0.9333** | **1.0000** | 0.1000 | 0.7481 |
| Hybrid + reranker | 0.6333 | **0.9333** | **1.0000** | 0.1000 | 0.7440 |
| Hybrid Full | 0.6333 | 0.8333 | 0.8500 | 0.0850 | 0.7056 |

The reranker was evaluated honestly: on this corpus it did **not** improve the
aggregate retrieval metrics over RRF.

### Cleanup verification

The completed live benchmark reported zero leftovers for:

- benchmark documents
- benchmark chunks
- benchmark organizations
- benchmark users
- Qdrant points

This confirms that the temporary benchmark data was removed after evaluation.

## 3. Security readiness

Implemented controls include:

- Argon2 password hashing
- constant-time login verification using a dummy hash
- JWT expiry enforcement
- supported HMAC algorithm validation
- refresh-token hashing, rotation, and revocation
- JTI denylisting
- per-email login throttling
- upload size/content-type/magic-byte validation
- guarded local file storage
- tenant-scoped PostgreSQL and Qdrant access
- organization-level RBAC
- audit logging with an allowlisted detail set
- generic internal-error responses with request IDs
- production fail-fast configuration validation
- no tracked production secrets
- dependency security auditing in CI

### Operational caveats

These are known architecture boundaries rather than hidden defects:

- Login throttling is per process. A multi-replica deployment needs shared rate
  limiting if a global login limit is required.
- Uploaded files use local filesystem storage. Multi-replica deployments need
  shared persistent storage or object storage.
- Background ingestion uses FastAPI `BackgroundTasks`, not a durable queue.
  Stale `PROCESSING` documents are recovered and can be retried, but a durable
  queue would be preferable for large-scale production workloads.
- No universal production throughput or availability claim is made.

## 4. Reliability readiness

The document lifecycle now includes explicit handling for:

- `PENDING → PROCESSING → READY`
- `PROCESSING → FAILED`
- `FAILED → PENDING` retry
- stale `PROCESSING → PENDING` recovery
- serialized replacement/deletion operations using PostgreSQL row locks
- processing lease refresh before external indexing
- Qdrant mutation only after the corresponding document row is locked

Normal retrieval exposes only chunks belonging to `READY` documents. This
prevents a document that is stuck or recovering from becoming normally
searchable through stale lifecycle state.

The system still does not pretend that PostgreSQL and Qdrant form a distributed
transaction. A process failure during an external-index operation can leave
operationally stale vectors; lifecycle state prevents those vectors from being
used normally, and cleanup/reprocessing handles the document path.

## 5. Evaluation limitations

The live retrieval benchmark is an engineering baseline, not a production SLA.

- The corpus is controlled and small compared with a real enterprise corpus.
- Retrieval metrics are not answer-quality metrics.
- The 93.33% headline is **Recall@5**, not accuracy.
- No human-rated helpfulness or fluency score is claimed.
- Local model latency is hardware-dependent.
- The benchmark does not establish production throughput or concurrency.
- The cross-encoder is not claimed to improve retrieval unless a future measured
  benchmark demonstrates that improvement.

Historical answer-quality runs remain documented as historical evidence and are
not substituted for the current retrieval benchmark.

## 6. Deployment requirements for real traffic

Before using NEXORA for real external traffic, the deployment should provide:

1. `ENVIRONMENT=production` with a fresh strong `JWT_SECRET_KEY`.
2. Secure PostgreSQL credentials and backups with a tested restore procedure.
3. Persistent Qdrant storage and persistent document storage.
4. TLS termination and explicit CORS configuration.
5. Shared rate limiting if multiple API replicas are deployed.
6. Durable background-job infrastructure if ingestion volume requires it.
7. Centralized logs/metrics/tracing and alerting.
8. Load testing at expected concurrency and documented capacity limits.
9. Production-grade model serving or a managed LLM provider.
10. Secret management outside the repository.

These are deployment requirements, not reasons to add unnecessary infrastructure
to the student project itself.

## 7. Final assessment

NEXORA should be presented as:

> **A production-oriented, multi-tenant RAG backend with tested security,
> lifecycle recovery, retrieval evaluation, and honest operational boundaries.**

It should **not** be presented as:

- a production SaaS serving real customers,
- a horizontally scaled distributed system,
- a measured high-throughput service,
- or a system with universally proven answer accuracy.

For the project portfolio and resume, the engineering baseline is complete.
Further work should only be added when it serves a specific learning or
production requirement.
