# Deployment Readiness

Assessment date: **2026-09-28**. Scope: the FINAL deployment-readiness audit of
NEXORA as it exists today. Every "Passed" item below was verified in this pass;
every "Not verified" item is reported honestly rather than assumed.

## Overall Status: READY WITH CONDITIONS

The **application** is production-grade and verified: tests pass, migrations
upgrade cleanly against real PostgreSQL, security controls are implemented and
reviewed, multi-tenant isolation is enforced at four layers, and the RAG pipeline
produces grounded, cited answers with measured quality.

NEXORA is **not** unconditionally "READY" because two things could not be
completed **in this environment**:

1. The **Docker production stack** (image build + compose boot + health/smoke
   test) could **not be verified** — the Docker daemon would not start on the
   audit machine. The compose *configuration* validated offline, but a live
   containerized boot was not observed.
2. A few **scale-out caveats** (per-process login throttle, local-disk upload
   storage, no dependency CVE scanning) are acceptable for a single-node
   deployment but should be addressed before multi-replica production traffic.

Per the project rule ("do not choose READY unless the evidence supports it" and
"do not deploy publicly unless the local production-like stack passes"), the
correct status is **READY WITH CONDITIONS**: deployable to a single node once the
Docker stack is verified on a machine with a working daemon, with the scale-out
items tracked as pre-production work.

## Passed (verified this pass)

- **Test suite:** 542 passed, 3 skipped. The 3 skips are
  `tests/test_migrations.py` (skipped only because `TEST_DATABASE_URL` was unset
  in that particular run); migration tests were separately verified against real
  PostgreSQL. `python -m compileall -q backend` clean. `git diff --check` clean.
- **Migrations:** linear Alembic chain, single head (`c3d9a1f0e5b7`, 16 revision
  files), clean upgrade from an empty PostgreSQL 17 database; `alembic heads`
  shows one head.
- **Retrieval benchmark (live):** hybrid_full Recall@1 = 0.6667, MRR = 1.0000;
  RRF-only 0.6500 / 0.9778; BM25 and dense 0.6333 / 0.9611. Cleanup proof: zero
  leftovers.
- **Answer-quality benchmark (live):** fact 30/30, citation 30/30, refusal 3/3 at
  both top_k=2 and top_k=10. Cleanup proof: zero leftovers.
- **Grounding/refusal:** both mechanisms observed — deterministic canned refusal
  (zero chunks above threshold, no LLM call) and model-judgement refusal.
- **Security review:** Argon2 hashing, constant-time login, exp-required JWT,
  SHA-256 refresh hashes with rotation/revocation, login throttle → 429,
  magic-byte upload validation, path-traversal-guarded storage, audit detail
  allowlist, uniform error messages, `.env` untracked, no tracked secrets.
- **Production config fail-fast:** verified that `validate_production_safety`
  rejects weak JWT secrets, CORS wildcards, and under-configured LLM providers at
  startup.
- **Compose configuration:** `docker compose -f docker-compose.prod.yml config -q`
  passes with throwaway env, and the required-variable guards
  (`POSTGRES_PASSWORD`, `JWT_SECRET_KEY`) abort startup when unset.

## Warnings (acceptable for single-node, fix before scale-out)

- **Login throttle is per-process.** With multiple API replicas, each throttles
  independently; a global limit needs a shared store. Single-node: fine.
- **Uploads use local-disk storage** (`STORAGE_BACKEND=local`). Multi-replica
  needs a shared/persistent volume or object storage.
- **Background ingestion uses FastAPI `BackgroundTasks`**, not a durable queue.
  A process death mid-processing leaves the document `failed` (retriable), but
  in-flight work is not resumed automatically.
- **No dependency CVE scanning in CI.** Dependencies are pinned; adding
  `pip-audit`/Dependabot is recommended.
- **Evaluation corpus is small** (10 docs, 30 questions). Metrics are indicative.

## Blockers (must clear before public deployment)

- **Docker production stack not verified (environmental).** The image build and
  a live compose boot + health/smoke test must be run on a machine with a working
  Docker daemon. This is an environment limitation on the audit machine, not a
  known code defect — but it is a blocker for "deploy publicly" until cleared.
  Exact commands: see [deployment.md](deployment.md) → "Exact commands to finish
  Docker verification".

No code-level deployment blockers were identified.

## Security

Implemented and reviewed (details in [security.md](security.md)): Argon2 password
hashing; constant-time login with a dummy hash; JWT HS256 with required `exp`;
refresh tokens stored as SHA-256 with rotation and revocation; per-email login
throttle (429 + `Retry-After`); two-level RBAC (platform `admin`/`member`,
organization `owner`/`admin`/`member`); tenant isolation at API/service/Postgres/
Qdrant layers plus a post-query re-check; upload size/content-type/magic-byte
validation; path-traversal-guarded storage; ORM/parameterized queries; typed
errors mapped to static messages; generic 500 handler that hides internals and
returns `X-Request-ID`; request logging that never records bodies/headers/
secrets; append-only audit log with an allowlisted detail set; production
fail-fast config validation; no tracked secrets in git.

Residual: per-process throttle and no API-wide rate limiting (see Warnings).

## Performance

Single-run local measurements (Apple Silicon arm64, Ollama `qwen3:8b`,
`OLLAMA_THINK=false`), 10-doc corpus, 30 questions:

- **E2E RAG (top_k=2):** total mean 10.47s / median 9.37s / p95 18.79s /
  max 30.99s; generation mean 9.04s / p95 15.19s.
- **E2E RAG (top_k=10):** total mean 6.56s / median 4.22s / p95 16.99s;
  generation mean 5.88s.
- Latency is dominated by local 8B LLM inference. `generation min = 0.00s` on the
  no-LLM canned-refusal path.

**Not measured:** TTFT distribution, per-stage component latency,
throughput/concurrency, token counts, dollar cost. These are indicative local
numbers, **not** a production SLA. Details in [performance.md](performance.md).

## Evaluation

- **Retrieval:** hybrid (RRF + cross-encoder) measurably beats BM25-only and
  dense-only on Recall@1 and MRR (see [retrieval.md](retrieval.md)). Honest
  margin: small, on a clean 30-question corpus.
- **Answer quality:** fact 1.0, citation 1.0, refusal 1.0. Both refusal paths
  exercised.
- **Limitations:** small corpus, clean prose, single run, no human-rated
  helpfulness. Details in [evaluation.md](evaluation.md).

## Infrastructure

- **Packaging:** multi-stage non-root `Dockerfile` (uvicorn:8000, healthcheck),
  `docker-entrypoint.sh` (waits for Postgres → `alembic upgrade head` → exec),
  `docker-compose.prod.yml` (API + postgres:17 + qdrant:v1.19.1, named volumes,
  only the API port published, required-secret guards), `.dockerignore`.
- **CI:** GitHub Actions (`.github/workflows/ci.yml`) — Postgres-only service,
  `alembic upgrade head`, `compileall`, `pytest -q` on push to `main` and PRs.
- **Runtime deps:** PostgreSQL 17, Qdrant, Ollama (or an OpenAI-compatible
  gateway). Embedding/reranker models are pulled by sentence-transformers on
  first use.
- **Verification gap:** containerized boot not observed this pass (daemon down).

## Production Requirements (before real traffic)

1. Run the Docker build + isolated compose boot + `/health` + authenticated smoke
   test on a machine with a working daemon ([deployment.md](deployment.md)).
2. Set strong, non-default secrets: `JWT_SECRET_KEY` (≥32 random chars),
   `POSTGRES_PASSWORD`. Provide via a secrets manager / `--env-file`, never
   committed.
3. Set `ENVIRONMENT=production` (enables fail-fast validation) and explicit
   `CORS_ORIGINS` (no wildcard).
4. Configure the active LLM provider fully (`OLLAMA_MODEL`, or
   `OPENAI_API_KEY` + `OPENAI_MODEL`).
5. Provision persistent volumes for Postgres, Qdrant, and uploads; enable
   Postgres backups and test a restore.
6. Put TLS termination and (ideally) shared rate limiting in front of the API.
7. Add dependency CVE scanning to CI.
8. Load-test at expected concurrency before launch (throughput not yet measured).

## Remaining Work

- **Blocker:** complete Docker production-stack verification (environmental).
- **Scale-out (only if multi-replica):** shared login-throttle store, object
  storage for uploads, durable ingestion queue.
- **Observability (optional, as needed):** metrics/tracing beyond request-id
  logging; aggregated TTFT/throughput measurement.
- **Quality (optional):** larger evaluation corpus; human-rated answer quality.
- **Security hygiene (recommended):** `pip-audit`/Dependabot in CI; periodic
  secret rotation.

None of the above are code defects; they are the honest gap between "verified on
a single local node" and "verified for public, multi-replica production."
