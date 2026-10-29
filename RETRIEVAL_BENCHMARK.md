# Retrieval Quality Benchmark

This file records the current live retrieval benchmark for NEXORA. The values
below are measured by `backend/evaluation/benchmark.py`; they are not estimated
or extrapolated.

## Current dataset

- **16 documents**
- **220 chunks** after production extraction and chunking
- **60 positive evaluation questions**
- **6 negative questions** used by the broader answer evaluation
- Ground truth is defined by the labeled evaluation cases and anchor text.

## Metrics

- `Recall@k` — fraction of relevant ground-truth chunks present in the top k.
- `Precision@k` — fraction of the top k results that are relevant.
- `MRR` — mean reciprocal rank of the first relevant result.

## Current live benchmark

Run:

```bash
HF_HUB_OFFLINE=1 .venv/bin/python -u -m backend.evaluation.benchmark --live
```

The benchmark uses the production ingestion/indexing path with PostgreSQL,
Qdrant, BGE-M3 embeddings, BM25, RRF, and the cross-encoder reranker. It creates
a temporary organization and removes the seeded data after evaluation.

| configuration | Recall@1 | Recall@5 | Recall@10 | Precision@10 | MRR |
|---|---:|---:|---:|---:|---:|
| BM25 | **0.6667** | 0.8667 | 0.9500 | 0.0950 | **0.7483** |
| Dense | 0.6333 | 0.8667 | **1.0000** | 0.1000 | 0.7334 |
| Hybrid RRF | 0.6333 | **0.9333** | **1.0000** | 0.1000 | 0.7481 |
| Hybrid + reranker | 0.6333 | **0.9333** | **1.0000** | 0.1000 | 0.7440 |
| Hybrid Full | 0.6333 | 0.8333 | 0.8500 | 0.0850 | 0.7056 |

## Observations

- **Recall@1 is not 93.33%.** The best current Recall@1 is 66.67% with BM25.
- The **93.33% result is Recall@5** for Hybrid RRF and Hybrid + reranker.
- Dense, Hybrid RRF, and Hybrid + reranker all reach **100% Recall@10**.
- The cross-encoder reranker does **not** improve the current aggregate retrieval
  metrics. Its MRR is 0.7440 versus 0.7481 for RRF.
- Therefore the benchmark should not be described as evidence that reranking
  improves retrieval. It is evidence that the reranker was evaluated and that
  its effect was neutral/slightly negative on this dataset.

## Cleanup proof

The completed live run reported:

- leftover documents: **0**
- leftover chunks: **0**
- leftover organizations: **0**
- leftover users: **0**
- leftover Qdrant points: **0**

## Historical benchmark

The repository previously used a 30-question / 10-document corpus. Its results
are historical only:

| configuration | Recall@1 | Recall@5 | Recall@10 | Precision@10 | MRR |
|---|---:|---:|---:|---:|---:|
| BM25 | 0.6333 | 1.0000 | 1.0000 | 0.1667 | 0.9611 |
| Dense | 0.6333 | 1.0000 | 1.0000 | 0.1667 | 0.9611 |
| Hybrid RRF | 0.6500 | 1.0000 | 1.0000 | 0.1667 | 0.9778 |
| Hybrid + reranker | 0.6667 | 0.9833 | 0.9833 | 0.1633 | 1.0000 |

These historical values must not be presented as the current benchmark.

## Limitations

The current benchmark is still controlled and relatively small compared with a
real enterprise corpus. It should be treated as an engineering baseline, not a
universal retrieval-quality or production-SLA claim.
