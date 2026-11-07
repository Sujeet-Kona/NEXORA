# Retrieval

Retrieval finds the most relevant document chunks before the LLM generates an
answer. NEXORA uses hybrid retrieval: dense vector search plus BM25, followed
by Reciprocal Rank Fusion (RRF), optional cross-encoder reranking, and a
relevance threshold.

## Pipeline

```text
question
   ├─► Dense retrieval (Qdrant / BGE-M3)
   └─► Lexical retrieval (BM25)
                │
                ▼
          RRF fusion (k=60)
                │
                ▼
       Cross-encoder reranking
                │
                ▼
        relevance threshold
                │
                ▼
        top RETRIEVAL_TOP_K
                │
                ▼
               LLM
```

Dense retrieval captures semantic similarity. BM25 captures exact terms,
identifiers, and names. RRF combines the ranked lists without requiring their
raw scores to be on the same scale.

The cross-encoder reads the question and candidate chunk together and assigns
a relevance score. Candidates below `RETRIEVAL_MIN_RELEVANCE` are dropped.

## Grounding and tenant filtering

If no chunk clears the relevance threshold, the RAG layer returns a deterministic
refusal without calling the LLM. This is one of the system's grounding guards.

Retrieval is organization-scoped at the vector and lexical stages, and returned
chunk IDs are re-checked against PostgreSQL with the organization scope before
the text reaches the reranker/LLM. Optional `document_ids` filtering is applied
through the retrieval path as well.

## Current live benchmark

The last measured live baseline used **16 documents, 220 chunks, and 60 positive
questions**. The current labeled set contains 62 positive questions. The
chunk-preservation repair requires a fresh live run before publishing a new
chunk count or updated metrics. The benchmark seeds a temporary organization
through the production ingestion and indexing path and cleans the seeded data
afterward.

Run:

```bash
HF_HUB_OFFLINE=1 .venv/bin/python -u -m backend.evaluation.benchmark --live
```

Current measured results:

| configuration | Recall@1 | Recall@5 | Recall@10 | Precision@10 | MRR |
|---|---:|---:|---:|---:|---:|
| BM25 | **0.6667** | 0.8667 | 0.9500 | 0.0950 | **0.7483** |
| Dense | 0.6333 | 0.8667 | **1.0000** | 0.1000 | 0.7334 |
| Hybrid RRF | 0.6333 | **0.9333** | **1.0000** | 0.1000 | 0.7481 |
| Hybrid + reranker | 0.6333 | **0.9333** | **1.0000** | 0.1000 | 0.7440 |
| Hybrid Full | 0.6333 | 0.8333 | 0.8500 | 0.0850 | 0.7056 |

### Interpretation

- **Recall@1 is 66.67% at best.** The 93.33% result is Recall@5.
- Hybrid RRF finds the relevant evidence within the top 5 for 93.33% of the
  evaluation questions and within the top 10 for 100% of them.
- The cross-encoder reranker does **not** improve the current benchmark: its
  Recall@1/5/10 matches RRF and its MRR (0.7440) is slightly below RRF (0.7481).
- Therefore NEXORA does not claim that reranking improved retrieval on the
  current dataset.
- These are benchmark-specific measurements, not production accuracy guarantees.

## Metrics in simple English

- **Recall@1:** how often the relevant ground-truth chunk appears in the first
  result.
- **Recall@5 / Recall@10:** how often relevant ground-truth chunks appear in the
  first 5 / 10 results.
- **Precision@10:** the fraction of the first 10 results that are relevant.
- **MRR:** the average reciprocal rank of the first relevant result. Higher is
  better; 1.0 means the first relevant result is ranked first for every case.
- **nDCG@10:** ranking quality with a logarithmic discount for lower-ranked
  relevant chunks.
- **Ground-truth hit rate@10:** fraction of questions with at least one labeled
  chunk in the first 10 results.
- **Empty retrieval rate:** fraction of questions returning no chunks.
- **Production context coverage:** recall, hit rate, empty-context rate, and mean
  context chunks at the configured `RETRIEVAL_TOP_K` limit, compared with
  the evaluation-only no-score-filter control.
- **Reranker zero-survivor rate / retention rate:** fraction of non-empty
  candidate pools completely filtered, and fraction of candidates retained.

## Cleanup verification

The completed current live run reported zero leftovers for:

- documents
- chunks
- organizations
- users
- Qdrant points

This confirms that the temporary benchmark data was removed after the run.

## Historical benchmark

The repository previously used a smaller 30-question / 10-document corpus.
Its results remain useful for historical comparison but are not the current
headline benchmark:

- BM25 Recall@1 0.6333, MRR 0.9611
- Dense Recall@1 0.6333, MRR 0.9611
- Hybrid RRF Recall@1 0.6500, MRR 0.9778
- Hybrid + reranker Recall@1 0.6667, MRR 1.0000

## Limitations

The current dataset is still small compared with a real enterprise corpus. It
contains clean labeled cases, so the benchmark should be treated as a controlled
engineering baseline rather than a general claim about retrieval quality.

## Cross-encoder score filtering and diagnostics

The cross-encoder returns a raw ranking logit. NEXORA applies a sigmoid
transformation so the stored score is bounded to [0, 1]; this transformation
preserves ordering but does **not** calibrate the value as a probability of
relevance. RETRIEVAL_MIN_RELEVANCE is therefore an operational cutoff, not a
probability guarantee.

Set LOG_LEVEL=DEBUG in the local environment and restart the API to
record each reranked candidate's chunk ID, page range, raw logit, sigmoid
score, configured/overridden threshold, and keep/drop decision. If every
candidate is filtered, NEXORA emits a warning with the candidate count and
threshold. These logs intentionally omit passage text and the user query.
Restore LOG_LEVEL=INFO after collecting the diagnostic trace.

The live retrieval benchmark now reports both the configured production
threshold and an evaluation-only no-score-filter control. This isolates the
effect of threshold filtering without changing the production default. Compare
the two configurations on the same seeded corpus before changing
RETRIEVAL_MIN_RELEVANCE.
