# Performance & Cost

All numbers here are **local, single-run measurements** on one machine. They are
**indicative**, not universal production performance and not an SLA. Per the
project rule, anything not measured is explicitly marked **"Not measured"**
rather than estimated.

## Test conditions

- **Machine:** local Apple Silicon (arm64) workstation. Exact GPU/RAM not
  recorded for this run.
- **LLM:** Ollama `qwen3:8b`, local, `OLLAMA_THINK=false` (reasoning trace
  disabled), `OLLAMA_NUM_PREDICT=256` (max output tokens).
- **Embeddings:** `BAAI/bge-m3` (1024-dim), local via sentence-transformers.
- **Reranker:** `cross-encoder/ms-marco-MiniLM-L-6-v2`, local.
- **Data stores:** PostgreSQL 17 (:5433), Qdrant 1.19.1 (:6333), both local.
- **Corpus:** 10 `.docx` files (~31 chunks); 30 positive + 3 negative questions.
- **Date:** 2026-09-28.

## End-to-end RAG latency

From `answer_benchmark.py` (question → retrieval → generation → answer):

| configuration | total mean | total median | total p95 | total max | gen mean | gen p95 |
|---------------|-----------|--------------|-----------|-----------|----------|---------|
| top_k=2 (production default) | 10.47s | 9.37s | 18.79s | 30.99s | 9.04s | 15.19s |
| top_k=10 | 6.56s | 4.22s | 16.99s | 26.00s | 5.88s | 16.52s |

- **"total"** = whole request (embed query + dense + BM25 + RRF + rerank + LLM).
- **"generation"** = LLM time only.
- `generation min = 0.00s` occurs on the deterministic refusal path (zero chunks
  above threshold → canned answer, **no LLM call**). Two of three negative cases
  hit this path.
- The dominant cost is **LLM generation** on a local 8B model. Retrieval
  (embedding + Qdrant + BM25 + rerank) is the smaller "total − generation" gap.

**Do not** conclude top_k=10 is faster than top_k=2 — this is single-run noise on
a local LLM (per-case totals ranged 2.1s–26s). More context normally means more
tokens to generate.

### TTFT (time to first token)

The streaming path measures `ttft_ms` per request and reports it in the terminal
`done` SSE event. The batch `answer_benchmark.py` harness above reports
total/generation latency but does **not** aggregate a separate TTFT
distribution — **TTFT p50/p95: Not measured** in this run. To capture it, use
the `/query/stream` endpoint and read `timing.ttft_ms` from the `done` event.

## Component-level latency

Individual stage timings (ingestion throughput, embedding-only, dense-only,
BM25-only, RRF-only, rerank-only) were **not separately instrumented** in this
pass — **Not measured**. The harness measures retrieval as part of the combined
"total" minus "generation". If you need a per-stage breakdown, add timers around
each retriever in `hybrid_retrieval_service.py`.

What is known qualitatively:

- **Ingestion** is off the request path (FastAPI BackgroundTask), so upload
  returns immediately; extraction + chunking + embedding + Qdrant upsert happen
  asynchronously. Embedding batches are 32 chunks; Qdrant upsert batches are 32
  points.
- **First query** after process start pays a one-time model-load cost
  (sentence-transformers + reranker weights); subsequent queries reuse the cached
  singletons (`@lru_cache`).

## Throughput / concurrency

**Not measured.** No load test (e.g. concurrent queries, requests/second) was run
in this pass. The login throttle and BM25 cache are thread-safe, and DI
singletons are per-process (replica-safe), but no empirical concurrency numbers
are claimed.

## Cost

### Token usage

Per-request input/output/embedding token counts were **not instrumented** in the
benchmark — **Not measured**. Configuration bounds that are known:

- Output is capped at `OLLAMA_NUM_PREDICT=256` tokens per answer.
- Input to the LLM is the grounded system prompt + the top `RETRIEVAL_TOP_K`
  (default 2) numbered chunks + the question.
- Each query embeds the question once (1 × 1024-dim vector); each chunk is
  embedded once at ingestion.

### Money cost

NEXORA's default provider is **Ollama running a local model** (`qwen3:8b`). This
means:

- **No API token charge.** There is no per-token bill to a hosted provider — the
  model runs on your own hardware.
- **There is still a real compute cost.** Local inference consumes GPU/CPU,
  memory, and electricity. An 8B model is modest but not free; sustained load
  needs adequately sized hardware. This cost is your infrastructure bill, not a
  per-query fee.
- **Do not claim "cost savings" as a measured number.** NEXORA was not run
  against a priced hosted API in this pass, so no dollar comparison exists. The
  honest statement is: *local inference has no per-token API charge; it shifts
  cost to your own compute.*

If you switch `LLM_PROVIDER=openai` (or an OpenAI-compatible gateway), you pay
that provider's per-token rates; NEXORA does not currently meter or report spend,
so cost tracking would be on the provider side.

## Summary of what is and is not measured

| Metric | Status |
|--------|--------|
| E2E RAG total latency (mean/median/p95/max) | Measured (single run) |
| LLM generation latency | Measured (single run) |
| Fact / citation / refusal accuracy | Measured (1.0 / 1.0 / 1.0) |
| Retrieval Recall@k / Prec@k / MRR | Measured |
| TTFT distribution | Not measured |
| Per-stage component latency | Not measured |
| Throughput / concurrency | Not measured |
| Token counts per request | Not measured |
| Dollar cost / cost savings | Not measured (local inference = no API charge) |
