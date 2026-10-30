# Historical Answer-Quality Benchmark

> **Historical artifact — not the current NEXORA headline benchmark.**
>
> This document records an earlier end-to-end answer-quality run so that the
> repository preserves the measurement history. The current retrieval benchmark
> is documented in [`docs/evaluation.md`](docs/evaluation.md) and
> [`RETRIEVAL_BENCHMARK.md`](RETRIEVAL_BENCHMARK.md).

## Purpose

This run measured the full RAG path:

`question → hybrid retrieval → RRF → cross-encoder rerank → context → Ollama → grounded answer`

It was executed against live PostgreSQL, Qdrant, and Ollama rather than using
mocked retrieval or estimated values.

## Historical dataset

- 10 benchmark documents
- 31 chunks after production extraction and chunking
- 30 positive evaluation questions
- 3 negative/refusal questions
- production upload → extraction → chunking → embedding → Qdrant indexing path

The current evaluation corpus is larger and should be used for current retrieval
claims: 16 documents, 220 chunks, and 60 retrieval questions.

## Historical environment

- PostgreSQL 17
- Qdrant 1.19.1
- `BAAI/bge-m3` embeddings, 1024 dimensions
- BM25 + RRF
- `cross-encoder/ms-marco-MiniLM-L-6-v2`
- Ollama `qwen3:8b`
- `OLLAMA_THINK=false`
- `OLLAMA_NUM_PREDICT=256`

## Historical results

| configuration | fact | citation | refusal | total p95 | generation mean |
|---|---:|---:|---:|---:|---:|
| top_k=2 | 1.0000 | 1.0000 | 1.0000 | 15.28s | 10.09s |
| top_k=10 | 1.0000 | 1.0000 | 1.0000 | 73.10s | 45.41s |

Historical latency detail:

| configuration | metric | mean | median | p95 | min | max |
|---|---|---:|---:|---:|---:|---:|
| top_k=2 | total | 10.85s | 10.74s | 15.28s | 2.57s | 39.12s |
| top_k=2 | generation | 10.09s | 10.30s | 14.54s | 2.14s | 30.99s |
| top_k=10 | total | 46.23s | 45.62s | 73.10s | 32.68s | 74.56s |
| top_k=10 | generation | 45.41s | 44.93s | 71.55s | 31.87s | 73.25s |

The seeded benchmark data was removed after the run: documents, chunks,
organization, users, and Qdrant points all reported zero leftovers.

## Interpretation

These measurements showed that, on that older corpus, increasing the context
width from 2 to 10 did not improve the deterministic fact/citation checks but
could substantially increase local generation latency.

The result is useful as historical engineering evidence only. It does **not**
establish a production answer-quality SLA or universal answer accuracy.

## Important correction to the original run

The original run initially used a refusal-marker detector that did not recognize
some genuine model refusals. The detector was subsequently corrected and covered
by regression tests. The corrected refusal score was therefore deterministic
re-scoring of the captured answers, not a new model run.

This is why the historical result is retained transparently rather than being
presented as a fresh benchmark.

## Current benchmark

For the current measured retrieval baseline, use:

- [`docs/evaluation.md`](docs/evaluation.md)
- [`docs/evaluation-reproducibility.md`](docs/evaluation-reproducibility.md)
- [`RETRIEVAL_BENCHMARK.md`](RETRIEVAL_BENCHMARK.md)

Current retrieval results include BM25, dense, RRF, cross-encoder reranking, and
cleanup verification over 16 documents / 220 chunks / 60 evaluation questions.
