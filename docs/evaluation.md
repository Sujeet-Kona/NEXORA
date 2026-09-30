# Evaluation

NEXORA ships two benchmark harnesses under `backend/evaluation/`. Both produce
**real measurements** and clean up all seeded data afterward (with a printed
proof). Nothing here is estimated.

- `benchmark.py` — retrieval quality (offline BM25 comparison + `--live`
  dense/BM25/hybrid through the real pipeline).
- `answer_benchmark.py` — end-to-end answer quality (fact / citation / refusal)
  and latency, through the real RAG pipeline with a live LLM.

## Dataset

Defined in `backend/evaluation/dataset.py`:

- **Corpus:** the 10 policy/report `.docx` files in `benchmark-data/`
  (attendance, emergency alert system, employee conduct, expense, information
  security, leave, password authentication, remote work, travel, workplace
  safety). After production extraction + chunking (size 3000 / overlap 400) this
  is ~31 chunks.
- **30 positive cases** (`EvaluationCase`): 3 per document. Each has a
  `question`, the source `document`, an `anchor` sentence, and one or more
  `expected` answer facts (e.g. `("20 days", "twenty days")`).
- **3 negative cases** (`NegativeCase`): topics verified **absent** from the
  corpus (cryptocurrency investment policy, paid parental leave weeks, gym
  reimbursement). These test that the system **refuses** instead of inventing an
  answer.
- **Ground truth:** every chunk of the labeled document whose text contains the
  case's anchor sentence (1–2 relevant chunks per case).

## Metrics (what they mean)

- **Fact accuracy** — does the answer contain one of the expected facts? Matched
  case-insensitively after whitespace normalization (`fact_matches`).
- **Citation accuracy** — does the answer carry a valid inline `[n]` citation
  that maps to a real source?
- **Refusal rate** — for negative cases, does the system decline? Detected by a
  lexicon of refusal phrasings (`REFUSAL_MARKERS`, e.g. "do not contain enough
  information", "does not provide information", "not specified", "insufficient",
  "cannot answer"). The lexicon was deliberately broadened to also catch
  "...does not contain information about X" (without the word "enough"), which
  the model emits just as often.
- **Recall@k / Prec@k / MRR** — standard IR metrics; see
  [retrieval.md](retrieval.md) for plain-English definitions.

## Answer-quality results (measured 2026-09-28)

Run: `.venv/bin/python -m backend.evaluation.answer_benchmark` against local
Postgres 17 (:5433) + Qdrant 1.19.1 (:6333) + Ollama `qwen3:8b` (:11434),
`OLLAMA_THINK=false`, on a local Apple Silicon (arm64) workstation. **Single
run — indicative, not a production SLA.**

| configuration | fact | citation | refusal | total p95 | gen mean |
|---------------|------|----------|---------|-----------|----------|
| top_k=2 (production default) | 30/30 = 1.0000 | 30/30 = 1.0000 | 3/3 = 1.0000 | 18.79s | 9.04s |
| top_k=10 (baseline K)        | 30/30 = 1.0000 | 30/30 = 1.0000 | 3/3 = 1.0000 | 16.99s | 5.88s |

Full latency distributions:

- **top_k=2** — total: mean 10.47s, median 9.37s, p95 18.79s, min 0.61s,
  max 30.99s. generation: mean 9.04s, median 8.11s, p95 15.19s, min 0.00s,
  max 22.18s.
- **top_k=10** — total: mean 6.56s, median 4.22s, p95 16.99s, min 0.68s,
  max 26.00s. generation: mean 5.88s, median 3.91s, p95 16.52s, min 0.00s,
  max 25.38s.

Cleanup proof: 0 leftover documents, chunks, organizations, users, and Qdrant
points.

### Reading these numbers honestly

- **Fact / citation / refusal are all perfect (1.0)** on this small, clean
  corpus: every answer contained the expected fact, carried a valid citation, and
  every negative case was refused.
- **`generation min = 0.00s` is real, not a bug.** Two of the three negative
  cases retrieve **zero** chunks above the relevance threshold, so the
  deterministic refusal path returns the canned answer **without calling the
  LLM** (~0s generation). The third negative (parental leave) *did* retrieve
  chunks but the model judged them insufficient and refused in its own words
  (a real LLM call). Both refusal mechanisms are exercised.
- **Do not read top_k=10 as "faster" than top_k=2.** These are single-run
  measurements on a local LLM; per-run variance is large (one top_k=10 case took
  26s, another 2.1s). More context generally means more tokens to generate. The
  p95 difference here is run-to-run noise, not a real speed advantage.
- The corpus is 30 questions over 10 short documents — a **small** set. One case
  is ±0.033 on aggregate metrics.

## Retrieval-quality results (measured 2026-09-28)

See [retrieval.md](retrieval.md) for the full table. Headline: `hybrid_full`
(RRF + cross-encoder) reaches **Recall@1 = 0.6667** and **MRR = 1.0000**,
beating BM25-only and dense-only (both Recall@1 0.6333, MRR 0.9611) and RRF-only
(Recall@1 0.6500, MRR 0.9778).

## Reproducing

```bash
# retrieval (offline BM25 comparison; no DB/Qdrant needed)
.venv/bin/python -m backend.evaluation.benchmark

# retrieval (live: seeds a real org through Postgres + Qdrant, then cleans up)
DATABASE_URL=postgresql+psycopg://user:pass@localhost:5433/nexora_bench \
  OLLAMA_THINK=false \
  .venv/bin/python -m backend.evaluation.benchmark --live

# end-to-end answer quality + latency (needs Postgres + Qdrant + Ollama)
DATABASE_URL=postgresql+psycopg://user:pass@localhost:5433/nexora_bench \
  OLLAMA_THINK=false \
  .venv/bin/python -m backend.evaluation.answer_benchmark
```

Both live harnesses create a throwaway organization, run the cases, and then
delete everything they created (printing the zero-leftover proof). Point
`DATABASE_URL` at a **scratch** database, not production data.

## Limitations

- Small corpus (10 docs, ~31 chunks, 30 questions). Results are indicative.
- Clean, well-separated prose; real enterprise corpora are noisier.
- Single-run latency on one local machine; not a throughput or SLA claim.
- No human-rated answer quality (helpfulness/fluency) — only fact, citation, and
  refusal checks.
