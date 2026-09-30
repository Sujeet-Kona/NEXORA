# Interview Notes

Talking points for explaining NEXORA in a technical interview. Everything here
is grounded in what the code actually does and the numbers actually measured.
Use the "honest limitations" section to show engineering maturity — interviewers
value knowing the edges of your system.

## 30-second pitch

"NEXORA is a secure, multi-tenant enterprise RAG platform. Tenants upload PDF or
DOCX documents; the system extracts and chunks the text, embeds it with BGE-M3
into Qdrant, and answers questions using **hybrid retrieval** — dense vectors
plus BM25, fused with Reciprocal Rank Fusion and reranked by a cross-encoder.
Answers are **grounded**: the LLM must cite the retrieved passages, and if no
passage is relevant enough the system refuses instead of hallucinating. It's a
FastAPI modular monolith with JWT auth, Argon2 passwords, organization-level
RBAC, tenant isolation enforced at four layers, and an append-only audit log."

## Architecture decisions worth defending

- **Modular monolith, not microservices.** The workload (document Q&A for a
  bounded tenant count) doesn't need distributed infra. One process is simpler
  to secure, deploy, and test. Layers: API → dependencies → services →
  repositories → stores. All business logic in services keeps it unit-testable
  with fakes.
- **Three stores, each for its job.** Postgres = source of truth (ownership,
  metadata, chunk text, audit). Qdrant = vector similarity index (treated as
  *untrusted*). Ollama = generation.
- **Postgres is authoritative over Qdrant.** After Qdrant returns candidate ids,
  chunks are re-fetched from Postgres filtered by organization. A stray vector
  can't leak another tenant's text. This "filter in the index, verify in the
  source of truth" pattern is the key isolation defense.
- **Lazy singletons** (`@lru_cache`) for the embedding model, Qdrant client, and
  LLM client → fast startup, `/health` without heavy deps, per-process caches
  that are replica-safe.
- **No LangChain/LangGraph.** An earlier graph implementation was removed; the
  RAG flow is plain Python — easier to debug and test. Only focused utilities
  remain (`langchain-text-splitters`, `langchain-huggingface`).

## Hard problems and how they were solved

1. **Grounding / anti-hallucination.** Two independent refusals: (a)
   deterministic — if zero chunks clear the reranker relevance threshold, return
   a canned refusal **without calling the LLM**; (b) model judgement under a
   grounded prompt. Plus citation validation that strips `[n]` markers pointing
   at no real source. Measured refusal rate on out-of-corpus questions: **3/3**.
2. **Constant-time login.** Always run exactly one Argon2 verify (dummy hash for
   unknown users) so timing doesn't reveal which emails are registered. Uniform
   401 messages reinforce this.
3. **Tenant isolation across two stores.** Enforced at API, service, Postgres,
   and Qdrant layers, with payload indexes on `organization_id`/`document_id`
   and tenant-scoped deletes. Cross-tenant tests prove no leakage.
4. **BM25 correctness.** A regex word tokenizer (`\w+` on lowercased text) fixed
   query terms that previously glued to punctuation; zero-term-overlap chunks are
   filtered. This lifted offline Recall@1 from 0.60 to 0.6333 and MRR from 0.9444
   to 0.9611.
5. **Page-level citations.** Chunking maps character offsets back to source
   pages so citations carry `page_start`/`page_end` (PDF); DOCX is one logical
   page.
6. **Secret-safe audit logging.** An allowlist of detail keys
   (`version, file_size, content_type, status, role, target_user_id`) means the
   audit trail never captures passwords, tokens, bodies, headers, prompts, or
   document content. Audit writes are best-effort so they can't break a primary
   operation.

## Numbers to quote (measured 2026-09-28, local, single run)

- **Tests:** 542 passed, 3 skipped (migration tests skip without
  `TEST_DATABASE_URL`). `compileall` clean; `git diff --check` clean.
- **Migrations:** linear chain, single head, verified upgrade against real
  PostgreSQL 17.
- **Retrieval (30 cases, 10 docs):** hybrid_full **Recall@1 = 0.6667, MRR =
  1.0000**, vs BM25/dense Recall@1 0.6333 / MRR 0.9611 and RRF-only 0.6500 /
  0.9778.
- **Answer quality:** fact **30/30**, citation **30/30**, refusal **3/3** at
  top_k=2 and top_k=10.
- **Latency (top_k=2):** total mean 10.47s / median 9.37s / p95 18.79s /
  max 30.99s; generation mean 9.04s. Dominated by local 8B LLM inference.

Always preface latency/accuracy with "on a small clean corpus, single local run,
indicative — not a production SLA."

## Metrics explained simply (if asked)

- **Recall@1** — fraction of the *should-find* chunks that landed in the very top
  result. Can't be 1.0 when a question has 2 relevant chunks.
- **MRR** — average of `1/rank` of the first relevant chunk. MRR 1.0 = the right
  chunk was #1 for every question.
- **Fact / citation / refusal accuracy** — does the answer contain the expected
  fact, carry a valid citation, and (for unanswerable questions) decline.

## Security talking points

Argon2 hashing; JWT HS256 with required `exp`; refresh tokens stored as SHA-256
with rotation + revocation; per-email login throttle → 429 + `Retry-After`;
production fail-fast config validation (JWT strength, no CORS wildcard, LLM
provider configured); magic-byte + content-type + size upload validation;
path-traversal-guarded storage; ORM/parameterized queries (no SQLi); static
error messages (no internal leakage); request-id correlation without logging
bodies/secrets; `.env` untracked, no tracked secrets.

## Honest limitations (say these proactively)

- **Login throttle is per-process.** Behind multiple replicas it isn't a global
  limit; a shared store (e.g. Redis) would be needed. Deliberately out of scope
  for the monolith.
- **Local disk storage only.** Multi-replica deployments need a shared/persistent
  volume or object storage (only the `local` backend is implemented).
- **No OCR / images / PDF tables.** Only text-based PDF and DOCX (incl. DOCX
  tables). Don't overclaim document intelligence.
- **Small evaluation set.** 30 questions over 10 short docs; one case is ±0.033.
- **Not measured:** TTFT distribution, per-stage latency, throughput/concurrency,
  token counts, dollar cost. Local inference has no per-token API charge but
  isn't free (compute/GPU/electricity).
- **No dependency CVE scanning in CI** (deps are pinned; a `pip-audit` step is a
  recommended addition).
- **Background ingestion uses FastAPI BackgroundTasks**, not a durable queue —
  work in flight is lost if the process dies mid-processing (the document ends
  `failed` and can be retried).

## Likely follow-up questions and crisp answers

- **"Why hybrid over pure vector search?"** BM25 catches exact keywords/IDs that
  embeddings blur; vectors catch paraphrase that keywords miss. RRF fuses them by
  rank (scale-free), and a cross-encoder reranks the small candidate set. Measured
  MRR went 0.9611 → 0.9778 (RRF) → 1.0000 (+rerank) on our benchmark.
- **"How do you prevent cross-tenant leakage?"** Four layers of `organization_id`
  scoping plus a Postgres re-check of every Qdrant hit; Qdrant is treated as
  untrusted.
- **"How do you stop hallucinations?"** Grounded prompt + relevance threshold
  with a no-LLM canned refusal + citation-marker validation. Refusal measured 3/3
  on out-of-corpus questions.
- **"Why a monolith?"** Right-sized for the workload; simpler to secure and
  operate. Horizontal scale is still possible with stateless replicas (per-process
  caches), subject to the throttle/storage caveats above.
- **"What would you add for real production?"** Shared rate limiting, object
  storage, a durable ingestion queue, dependency CVE scanning, distributed
  tracing/metrics, and load testing — only as real requirements justify them.
