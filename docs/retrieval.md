# Retrieval

Retrieval is the step that finds the most relevant chunks of your documents for
a question, before the LLM writes an answer. NEXORA uses **hybrid retrieval**:
it combines two different search strategies, merges them, and reranks the result.

## The pipeline

```
question
   │
   ├─► Dense retrieval  (Qdrant vector similarity)   → top RETRIEVAL_DENSE_TOP_K (10)
   │
   └─► Lexical retrieval (BM25 keyword match)        → top RETRIEVAL_LEXICAL_TOP_K (10)
                     │
                     ▼
              RRF fusion (k = 60)                     → top RETRIEVAL_RERANK_TOP_K (8)
                     │
                     ▼
        Cross-encoder rerank + relevance threshold    → drop < RETRIEVAL_MIN_RELEVANCE (0.5)
                     │
                     ▼
              top RETRIEVAL_TOP_K (2) chunks → sent to the LLM
```

### Dense retrieval (semantic)

The question is embedded with **BGE-M3** (`BAAI/bge-m3`, 1024-dim, normalized
cosine) and Qdrant returns the nearest chunk vectors, filtered by
`organization_id` (and optionally by `document_ids`). This finds chunks that
*mean* the same thing as the question, even without shared keywords.

### Lexical retrieval (keyword, BM25)

`BM25Okapi` scores chunks by exact term overlap with the question. This catches
precise keywords, identifiers, and names that a vector search can blur. The
index is per-organization, cached, and invalidated when chunks change.

### RRF fusion

**Reciprocal Rank Fusion** merges the two ranked lists. For each chunk, RRF adds
`1 / (k + rank)` across the lists it appears in, with `k = 60`. A chunk ranked
high by *both* retrievers rises to the top. RRF is rank-based, so it does not
need the two scores to be on the same scale.

### Cross-encoder rerank

The fused candidates are scored by a **cross-encoder**
(`cross-encoder/ms-marco-MiniLM-L-6-v2`), which reads the question and each chunk
together and outputs a relevance score (passed through a sigmoid). Chunks below
`RETRIEVAL_MIN_RELEVANCE` (default 0.5) are **dropped**. The survivors are
truncated to `RETRIEVAL_TOP_K` (default 2).

Reranking is more accurate than either first-stage retriever because a
cross-encoder sees the query and passage jointly, but it is slower — so it is
only applied to a small fused candidate set.

## Why the relevance threshold matters (grounding)

If **no** chunk clears the relevance threshold, retrieval returns an empty set.
The RAG layer then returns a canned refusal **without calling the LLM** (see
[rag-pipeline.md](rag-pipeline.md)). This is the first line of defense against
hallucination: when the documents do not actually contain the answer, NEXORA
says so instead of inventing one.

## Document filtering

The query accepts an optional `document_ids` list to restrict retrieval to
specific documents. The filter is applied at the dense stage, the lexical stage,
and the Postgres re-check, so chunks from other documents never reach the
reranker or the LLM. An empty list is rejected with **422**; omitting it searches
all of the organization's documents.

## Retrieval quality — measured

Numbers below are **real measurements**, re-run on **2026-09-28** with
`backend/evaluation/benchmark.py --live` against local Postgres 17 + Qdrant
1.19.1, real BGE-M3 embeddings, BM25Okapi, RRF (k=60), and the MiniLM
cross-encoder.

**Corpus:** the 10 policy/report `.docx` files in `benchmark-data/` (10
documents, ~31 chunks after production extraction + chunking at size 3000 /
overlap 400). **Questions:** 30 labeled cases (3 per document). **Ground truth:**
every chunk of the labeled document containing the case's anchor sentence
(1–2 relevant chunks per case).

| config       | Recall@1 | Recall@5 | Recall@10 | Prec@10 | MRR    |
|--------------|----------|----------|-----------|---------|--------|
| bm25         | 0.6333   | 1.0000   | 1.0000    | 0.1667  | 0.9611 |
| dense        | 0.6333   | 1.0000   | 1.0000    | 0.1667  | 0.9611 |
| hybrid_rrf   | 0.6500   | 1.0000   | 1.0000    | 0.1667  | 0.9778 |
| hybrid_full  | 0.6667   | 0.9833   | 0.9833    | 0.1633  | 1.0000 |

Cleanup proof after the run: 0 leftover documents, 0 chunks, 0 organizations, 0
users, 0 Qdrant points.

### What Recall@1 and MRR mean (simple English)

- **Recall@1** — of all the chunks that *should* have been found, what fraction
  showed up in the very **top 1** result. A case with 2 relevant chunks can
  never reach Recall@1 = 1.0 (both cannot sit in a single slot), which is why the
  best value here is 0.6667, not 1.0.
- **Recall@5 / Recall@10** — same idea, but counting the top 5 / top 10 results.
- **Prec@10** — of the top 10 results, what fraction were actually relevant.
  With only ~1.67 relevant chunks per case, the ceiling is ~0.1667 even for a
  perfect retriever.
- **MRR (Mean Reciprocal Rank)** — for each question, take `1 / rank` of the
  **first** relevant chunk (rank 1 → 1.0, rank 2 → 0.5, rank 3 → 0.33…), then
  average over all questions. **MRR = 1.0 means the first relevant chunk was at
  rank 1 for every single question.** It measures "how quickly does the right
  answer reach the top".

### What the numbers show

- On this corpus, BM25 and dense score **identically** in aggregate (they make
  different per-case mistakes that cancel out).
- **RRF fusion** improves Recall@1 (0.6333 → 0.6500) and MRR (0.9611 → 0.9778):
  chunks both retrievers like are promoted.
- **Adding the cross-encoder** (`hybrid_full`) improves further to Recall@1
  0.6667 and **MRR 1.0000** — a relevant chunk at rank 1 for every case.
- `hybrid_full` Recall@5/@10 (0.9833) is slightly below the others because it
  returns only the reranked top-`RETRIEVAL_TOP_K` set after applying the
  relevance threshold, so a second relevant chunk can be dropped in one case.
  This is the grounding guard working as designed, not a regression.

**Honest claim:** hybrid retrieval (RRF + rerank) measurably beats either
retriever alone on this benchmark for Recall@1 and MRR. The margin is small
because the corpus is 30 clean, well-separated questions over 10 short
documents; one case is ±0.033 on the aggregate metrics. Do not present these as
universal production numbers.

## Limitations

- 30 questions over 10 short documents is a **small** evaluation set.
- The corpus is clean prose; BM25's tokenizer improvements matter more on text
  with heavy punctuation, lists, or mixed formatting.
- These are **local** measurements on one machine, not a production SLA.
