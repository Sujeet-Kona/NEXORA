# Performance & Cost

> **Historical local measurements.** These numbers are preserved as engineering
> evidence from an earlier answer-quality run. They are not a production SLA
> and should not be used as the current benchmark headline.

NEXORA does not claim throughput, concurrency, availability, or cost savings
that have not been measured.

## Historical test conditions

- Machine: Apple Silicon arm64 workstation; exact GPU/RAM not recorded.
- PostgreSQL 17 and Qdrant 1.19.1 running locally.
- Embeddings: `BAAI/bge-m3`, 1024 dimensions.
- Reranker: `cross-encoder/ms-marco-MiniLM-L-6-v2`.
- LLM: Ollama `qwen3:8b`.
- `OLLAMA_THINK=false`.
- `OLLAMA_NUM_PREDICT=256`.
- Corpus: 10 documents / 31 chunks / 30 positive + 3 negative questions.

## Historical end-to-end latency

| configuration | total mean | total median | total p95 | total max | generation mean | generation p95 |
|---|---:|---:|---:|---:|---:|---:|
| top_k=2 | 10.85s | 10.74s | 15.28s | 39.12s | 10.09s | 14.54s |
| top_k=10 | 46.23s | 45.62s | 73.10s | 74.56s | 45.41s | 71.55s |

These values came from the historical `answer_benchmark.py` run. They should be
read as one-machine observations, not as expected latency for every deployment.

## What the measurements suggest

Generation dominated the request time on the local 8B model. The historical
run also showed that widening the context from top 2 to top 10 did not improve
the deterministic fact/citation checks on that corpus, while substantially
increasing generation time.

This supports keeping the production default small unless a future benchmark
shows that a larger context improves quality enough to justify its cost.

## Streaming latency

The streaming endpoint records `ttft_ms` and `total_ms` in its terminal `done`
event. A separate TTFT distribution was **not measured** in the historical run.

## Component latency

Per-stage latency for embedding, dense retrieval, BM25, RRF, and reranking was
not separately benchmarked in the historical run. No component-level numbers
are claimed here.

## Throughput and concurrency

**Not measured.** No load test establishing requests/second, concurrent users,
or saturation limits has been completed. The architecture is intentionally a
modular monolith rather than a measured distributed system.

## Cost

The default configuration uses local Ollama inference, so there is no hosted
API token charge. That does **not** mean the system has zero cost: local
inference consumes compute, memory, storage, and electricity.

No dollar-per-request or cost-savings figure has been measured. If an
OpenAI-compatible provider is configured, provider-side token pricing applies;
NEXORA does not currently meter that spend.

## Current evaluation source of truth

For current retrieval measurements, use:

- [`docs/evaluation.md`](evaluation.md)
- [`docs/evaluation-reproducibility.md`](evaluation-reproducibility.md)
- [`RETRIEVAL_BENCHMARK.md`](../RETRIEVAL_BENCHMARK.md)

The current retrieval benchmark covers 16 documents, 220 chunks, and 60
questions and reports Recall@1/5/10, Precision@10, and MRR for BM25, dense,
RRF, and reranked configurations.
