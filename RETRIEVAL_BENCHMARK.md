# Retrieval Quality Benchmark

Measured results for dense, sparse (BM25), and hybrid retrieval. All
numbers below are real measurements produced by
`backend/evaluation/benchmark.py` — no values are estimated or
extrapolated.

## Dataset

- Corpus: the 10 policy/report `.docx` files in `benchmark-data/`
  (10 documents, 31 chunks after production extraction and chunking:
  `RecursiveCharacterTextSplitter`, chunk size 3000, overlap 400).
- Questions: 30 labeled cases (3 per document) defined in
  `backend/evaluation/dataset.py`.
- Ground truth: every chunk of the labeled document whose text contains
  the case's anchor sentence (1–2 relevant chunks per case).

## Metrics

- `Recall@k` — fraction of the relevant chunks present in the top k.
- `Prec@k` — `|relevant ∩ top k| / k` (standard IR definition).
- `MRR` — mean over cases of `1 / rank` of the first relevant chunk.

Candidate depth is k = 10 for every configuration. Note these differ
from the pre-Phase-10 root script, whose "Recall@k" was hit-rate@k
(any relevant chunk in top k).

## Offline benchmark — BM25 fix impact

Compares pre-Phase-10 BM25 (whitespace tokenizer, zero-score chunks
kept) with the current BM25 (regex word tokenizer, term-overlap
filtering). No database, embeddings, or vector store involved.

Run: `.venv/bin/python -m backend.evaluation.benchmark`

| config       | Recall@1 | Recall@5 | Recall@10 | Prec@10 | MRR    |
|--------------|----------|----------|-----------|---------|--------|
| bm25_legacy  | 0.6000   | 0.9833   | 1.0000    | 0.1667  | 0.9444 |
| bm25         | 0.6333   | 1.0000   | 1.0000    | 0.1667  | 0.9611 |

Observations:

- The regex tokenizer fixes query terms that previously glued to
  adjacent punctuation in chunk text; Recall@1 improves 0.60 → 0.6333
  and MRR 0.9444 → 0.9611.
- The zero-score fix does not move Prec@10 on this corpus (all BM25
  scores are positive at 31 chunks); its benefit is preventing
  irrelevant chunks from filling RRF slots in small corpora, which is
  covered by unit tests instead.

## Live benchmark — BM25 vs dense vs hybrid

Seeds a fresh organization in Postgres and Qdrant through the
production pipeline (upload → extraction → chunking → bge-m3 embeddings
→ Qdrant indexing → BM25 index), runs all 30 cases, then removes all
seeded data (cleanup proof: 0 documents, 0 chunks, 0 organizations,
0 users, 0 Qdrant points).

Run: `.venv/bin/python -m backend.evaluation.benchmark --live`

Environment: local Postgres 17 + Qdrant 1.19.1 (Docker), real
`BAAI/bge-m3` embeddings (1024-dim, cosine), `BM25Okapi`, RRF fusion
(k = 60), `cross-encoder/ms-marco-MiniLM-L-6-v2` reranker. Measured
2026-09-23.

| config       | Recall@1 | Recall@5 | Recall@10 | Prec@10 | MRR    |
|--------------|----------|----------|-----------|---------|--------|
| bm25         | 0.6333   | 1.0000   | 1.0000    | 0.1667  | 0.9611 |
| dense        | 0.6333   | 1.0000   | 1.0000    | 0.1667  | 0.9611 |
| hybrid_rrf   | 0.6500   | 1.0000   | 1.0000    | 0.1667  | 0.9778 |
| hybrid_full  | 0.6667   | 1.0000   | 1.0000    | 0.1667  | 1.0000 |

Observations:

- BM25 and dense score identically on this corpus (30 clean,
  well-separated policy documents); the two retrievers make different
  mistakes per case but the aggregate metrics coincide.
- RRF fusion of the two improves Recall@1 (0.6333 → 0.6500) and MRR
  (0.9611 → 0.9778): chunks ranked high by both retrievers are
  promoted.
- The cross-encoder reranker improves further (Recall@1 0.6667, MRR
  1.0000 — a relevant chunk at rank 1 for every case).
- Recall@1 cannot reach 1.0 for cases with 2 relevant chunks (both
  cannot occupy rank 1); Recall@10 is 1.0 for every configuration.
- Prec@10 is identical across configurations because every config
  retrieves all relevant chunks within the top 10; with an average of
  1.67 relevant chunks per case the ceiling is 0.1667.

## Limitations

- 30 questions over 10 short documents is a small evaluation set;
  differences of one case are ±0.033 on the aggregate metrics.
- The corpus is clean prose; BM25's tokenizer fix has larger impact on
  text with heavy punctuation, lists, or mixed formatting.
