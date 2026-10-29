# Evaluation

NEXORA ships two benchmark harnesses under `backend/evaluation/`. Both produce
real measurements and clean up seeded data afterward, with a printed cleanup
proof.

- `benchmark.py` — retrieval quality. Offline mode evaluates BM25; `--live`
  seeds the real production ingestion/indexing path and compares BM25, dense,
  RRF, and reranked retrieval.
- `answer_benchmark.py` — end-to-end answer quality (fact, citation, refusal)
  and latency through the live RAG pipeline.

## Current evaluation dataset

The current dataset is defined in `backend/evaluation/dataset.py` and combines
policy cases with research-paper cases:

- **16 benchmark documents**
- **220 chunks** after production extraction and chunking
- **60 positive evaluation questions**
- **6 negative evaluation questions**
- Ground truth is based on labeled source documents and anchor text.

The negative cases test that the system refuses unsupported questions rather
than inventing an answer.

## Metrics

- **Recall@k** — fraction of relevant ground-truth chunks present in the top k.
- **Precision@k** — fraction of the top k results that are relevant.
- **MRR** — mean reciprocal rank of the first relevant result.
- **Fact accuracy** — whether the answer contains an expected fact.
- **Citation accuracy** — whether the answer contains a valid citation mapping
  to a returned source.
- **Refusal rate** — whether an out-of-corpus question is declined.

## Current live retrieval benchmark

Measured with:

```bash
HF_HUB_OFFLINE=1 .venv/bin/python -u -m backend.evaluation.benchmark --live
```

The live run seeds a temporary organization through the production document
pipeline, indexes the benchmark corpus in PostgreSQL/Qdrant, evaluates all 60
questions, and then removes the seeded data.

**Current result: 16 documents / 220 chunks / 60 evaluation questions.**

| configuration | Recall@1 | Recall@5 | Recall@10 | Precision@10 | MRR |
|---|---:|---:|---:|---:|---:|
| BM25 | **0.6667** | 0.8667 | 0.9500 | 0.0950 | **0.7483** |
| Dense | 0.6333 | 0.8667 | **1.0000** | 0.1000 | 0.7334 |
| Hybrid RRF | 0.6333 | **0.9333** | **1.0000** | 0.1000 | 0.7481 |
| Hybrid + reranker | 0.6333 | **0.9333** | **1.0000** | 0.1000 | 0.7440 |
| Hybrid Full | 0.6333 | 0.8333 | 0.8500 | 0.0850 | 0.7056 |

### Honest interpretation

- The best **Recall@1 is 66.67%**, achieved by BM25. The 93.33% figure is
  **Recall@5**, not Recall@1 and not answer accuracy.
- Hybrid RRF reaches **93.33% Recall@5** and **100% Recall@10** on this dataset,
  meaning the relevant evidence is generally present in the retrieved set even
  when it is not ranked first.
- The cross-encoder reranker **did not improve** Recall@1, Recall@5, Recall@10,
  or MRR on this current benchmark. Its MRR (0.7440) is slightly below RRF
  (0.7481). The project therefore does not claim that reranking improved this
  benchmark.
- The results are a baseline for this benchmark, not a universal production
  accuracy claim. The dataset is still small relative to a real enterprise
  corpus.

## Cleanup verification

The completed live run reported:

- leftover documents: **0**
- leftover chunks: **0**
- leftover organizations: **0**
- leftover users: **0**
- leftover Qdrant points: **0**

This verifies that the temporary benchmark organization and its indexed data
were removed after evaluation.

## Historical results

Older 30-question / 10-document measurements are retained only as historical
engineering evidence. They must not be presented as the current benchmark.

The historical live result was:

- BM25 Recall@1 0.6333, MRR 0.9611
- Dense Recall@1 0.6333, MRR 0.9611
- Hybrid RRF Recall@1 0.6500, MRR 0.9778
- Hybrid + reranker Recall@1 0.6667, MRR 1.0000

Those numbers came from the earlier corpus and are intentionally separated from
the current 60-question evaluation.

## Reproducing

```bash
# Offline retrieval benchmark
.venv/bin/python -m backend.evaluation.benchmark

# Live retrieval benchmark
HF_HUB_OFFLINE=1 .venv/bin/python -u -m backend.evaluation.benchmark --live

# End-to-end answer benchmark (requires the local runtime stack)
.venv/bin/python -m backend.evaluation.answer_benchmark
```

The live retrieval benchmark requires PostgreSQL, Qdrant, and the local
embedding/reranker models. It creates a throwaway organization and cleans up
its seeded data afterward. Run it against a scratch database/environment rather
than production data.

## Limitations

- The current retrieval benchmark has 60 positive questions over 16 documents;
  it is still much smaller and cleaner than a real enterprise corpus.
- Retrieval metrics do not equal end-to-end answer quality.
- No human-rated helpfulness or fluency score is claimed by the retrieval
  benchmark.
- Local model latency is hardware-dependent and is not a production SLA.
- No claim is made that reranking improves retrieval unless a measured
  benchmark demonstrates it.
