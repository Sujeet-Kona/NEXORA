# Answer Quality Benchmark

End-to-end answer-quality results for the full RAG pipeline: question →
hybrid retrieval (dense + BM25 + RRF) → cross-encoder rerank → context
selection → prompt → Ollama LLM → grounded answer with citations. All
numbers below are real measurements produced by
`backend/evaluation/answer_benchmark.py` against live Postgres, Qdrant
and Ollama — no values are estimated, extrapolated, or fabricated.

## Dataset

- Corpus: the 10 policy/report `.docx` files in `benchmark-data/`
  (10 documents, 31 chunks after production extraction and chunking),
  seeded through the real upload → extract → chunk → embed → index
  pipeline and removed again at the end of the run.
- Questions: the 30 labeled cases (3 per document) from
  `backend/evaluation/dataset.py`, each with a set of acceptable
  expected answer facts (`EvaluationCase.expected`).
- Negative questions: 3 cases whose topics are verified absent from the
  corpus (cryptocurrency investment policy, paid parental leave, gym
  membership reimbursement). These exercise the refusal path.

## Metrics

- **Fact accuracy** — fraction of the 30 labeled cases whose answer
  contains at least one expected fact (`fact_matches`, substring match
  after lower-casing and whitespace normalization).
- **Citation accuracy** — fraction of the 30 labeled cases whose
  returned sources include at least one ground-truth chunk (the chunks
  of the labeled document containing the case's anchor sentence).
  Citations come only from actually retrieved chunks.
- **Refusal rate** — fraction of the 3 negative cases where the model
  declines to answer (`indicates_refusal` against `REFUSAL_MARKERS`)
  instead of fabricating a fact.
- **Latency** — wall-clock seconds for the whole pipeline call
  (`total`) and for the LLM generation step alone (`generation`),
  reported as mean / median / p95 / min / max.

Two retrieval widths are measured so the effect of context size on
quality and latency is visible: the production default
(`RETRIEVAL_TOP_K = 2`) and the width used by the Phase 10 retrieval
baseline (`top_k = 10`).

## Environment

Local Postgres 17 + Qdrant 1.19.1 (Docker), real `BAAI/bge-m3`
embeddings (1024-dim, cosine), `BM25Okapi`, RRF fusion (k = 60),
`cross-encoder/ms-marco-MiniLM-L-6-v2` reranker, Ollama `qwen3:8b`
with `think = false`, `num_predict = 256`, timeout 300s. Measured
2026-09-25.

Run: `.venv/bin/python -m backend.evaluation.answer_benchmark`

## Results

| configuration                   | fact   | citation | refusal | total p95 | gen mean |
|---------------------------------|--------|----------|---------|-----------|----------|
| top_k=2 (production default)    | 1.0000 | 1.0000   | 1.0000  | 15.28s    | 10.09s   |
| top_k=10 (Phase 10 baseline K)  | 1.0000 | 1.0000   | 1.0000  | 73.10s    | 45.41s   |

Fact accuracy 30/30, citation accuracy 30/30, refusal rate 3/3 for both
configurations.

### Latency detail

| configuration | metric     | mean   | median | p95    | min    | max    |
|---------------|------------|--------|--------|--------|--------|--------|
| top_k=2       | total      | 10.85s | 10.74s | 15.28s | 2.57s  | 39.12s |
| top_k=2       | generation | 10.09s | 10.30s | 14.54s | 2.14s  | 30.99s |
| top_k=10      | total      | 46.23s | 45.62s | 73.10s | 32.68s | 74.56s |
| top_k=10      | generation | 45.41s | 44.93s | 71.55s | 31.87s | 73.25s |

### Cleanup proof

The seeded organization is fully removed at the end of the run:
leftover documents 0, chunks 0, organizations 0, users 0, Qdrant
points 0.

## Observations

- Answer quality is saturated at the production default: with only the
  top 2 reranked chunks as context, `qwen3:8b` answers all 30 labeled
  questions with a correct fact and cites a ground-truth chunk every
  time. Retrieval quality (Phase 10: Recall@10 = 1.0, MRR = 1.0 after
  rerank) carries through to generation.
- Widening context to top_k=10 does **not** improve fact or citation
  accuracy (already 1.0) but costs ~4.5× the generation latency
  (gen mean 10.09s → 45.41s; total p95 15.28s → 73.10s). The extra
  chunks lengthen the prompt the model must attend to without adding
  information it needs. This is direct evidence for keeping the
  production default small; top_k=2 is the right latency/quality
  trade-off on this corpus.
- The model refuses all 3 out-of-corpus questions rather than
  fabricating, e.g. *"The document context does not provide information
  about paid parental leave."* This is the generation prompt's
  grounding instruction working. It is distinct from the
  zero-retrieved-chunks canned refusal in `generation_service.py`:
  here chunks ARE retrieved (the closest, irrelevant ones) and the
  model itself declines. A dedicated relevance/grounding guard is
  still future work (brief Phase 15) — the current refusal relies on
  the model's own judgement, not an explicit retrieved-relevance
  threshold.
- Generation dominates total latency at both widths (gen mean is
  ~93–98% of total mean); retrieval + rerank add well under a second.
  Latency optimization should target generation (model size,
  num_predict, streaming), not retrieval.

## Methodology note — refusal lexicon

The live run that produced the numbers above scored the refusal path
with an initial `REFUSAL_MARKERS` lexicon that only matched
"does not contain **enough** information". The model's actual refusals
omit "enough" ("The document context does not contain information
about …", "… does not provide information about …"), so the run's raw
output printed `refusal 0/3` for both configurations even though all
six answers are genuine refusals.

The lexicon was corrected (adding the "enough"-less
contain/provide/include family, anchored on *information* so a
confident fabrication cannot match) and the fix is covered by
`tests/test_evaluation_metrics.py`:

- `test_refusal_markers_detect_context_lacking_answers` asserts the
  verbatim refusal texts from this run are detected.
- `test_refusal_markers_do_not_flag_grounded_or_fabricated_answers`
  asserts a grounded answer ("The minimum password length is 12
  characters.") and a confident fabrication ("Employees receive 12
  weeks of paid parental leave.") are **not** flagged.

The refusal rate of 1.0000 reported above is the corrected detector
applied to the same six captured answer texts (re-scoring is a
deterministic pure function of the answer string and the markers). A
fresh run of `answer_benchmark` with the corrected lexicon reproduces
3/3. The fact-accuracy, citation-accuracy, and latency numbers are
independent of the lexicon and are reported exactly as measured.

## Limitations

- 30 labeled questions plus 3 negatives over 10 short, clean policy
  documents is a small evaluation set; one case is ±0.033 on the
  aggregate rates. Quality on a larger, noisier, or more adversarial
  corpus is not established here.
- Fact accuracy uses substring matching against a hand-written set of
  acceptable facts per case; it rewards presence of the fact, not
  full answer correctness or fluency, and would not catch a correct
  fact embedded in an otherwise wrong answer.
- Latency is single-run wall-clock on one machine with the model warm
  in VRAM; it is indicative, not a controlled benchmark, and excludes
  cold-start model load.
- Refusal depends on the model's own judgement under the grounding
  prompt; there is no explicit retrieved-relevance threshold yet, so a
  model could still fabricate on a topic that loosely overlaps the
  corpus. That guard is deferred to brief Phase 15.
