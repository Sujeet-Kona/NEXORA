# Evaluation reproducibility

NEXORA keeps retrieval evaluation and end-to-end answer evaluation separate.
Neither benchmark is used as a substitute for automated correctness tests.

## Retrieval benchmark

Run the offline benchmark with:

```bash
python -m backend.evaluation.benchmark
```

Run the production-path retrieval benchmark with:

```bash
python -m backend.evaluation.benchmark --live
```

Live mode creates a fresh organization, uploads the checked-in benchmark
corpus through the production ingestion path, evaluates BM25, dense, RRF and
hybrid+rereank retrieval, then removes the seeded PostgreSQL rows, Qdrant
points and storage directory. The benchmark prints a cleanup proof for all
three stores.

Headline retrieval metrics are Recall@1, Recall@5, Recall@10, Precision@10
and MRR. The benchmark must report the corpus document count, chunk count and
question count before metrics are interpreted.

## Answer benchmark

Run the end-to-end benchmark with:

```bash
python -m backend.evaluation.answer_benchmark
```

It evaluates positive and negative cases separately. Positive cases measure
fact accuracy and citation accuracy. Negative cases measure refusal rate.
Latency is reported separately for the total pipeline and LLM generation.

A strong answer result requires both a correct fact and a grounded citation;
these should not be conflated with retrieval metrics. Refusal performance is
also reported independently because a system can retrieve well while still
answering an unanswerable question incorrectly.

## Interpretation rules

- Never mix offline BM25 numbers with live hybrid numbers.
- Never report historical benchmark numbers as current runtime measurements.
- Never describe fact/citation checks as human-quality evaluation; they are
  deterministic regression signals based on the checked-in labeled corpus.
- Report the corpus version and model configuration whenever benchmark results
  are copied into project documentation or a resume.
- Do not claim a benchmark passed unless the command completed against the
  required live dependencies and printed a zero-leftover cleanup proof.

The checked-in dataset is the source of truth for reproducibility. If the
corpus, expected answers, retrieval configuration, embedding model or LLM
configuration changes, benchmark results must be regenerated rather than
edited manually.
