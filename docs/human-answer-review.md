# Human review of answer quality

The automated answer benchmark currently includes lexical fact-match and
refusal-marker checks. Those checks are useful regression signals, but they
are not semantic judgments. Use this protocol when evaluating answer quality
with human reviewers.

## Review record

Store one JSON object per line in a local JSONL file. Do not commit reviewer
names, private customer documents, access tokens, or other sensitive material.
Use stable anonymous reviewer IDs (for example, `reviewer-1`) only when
multiple reviewers need to be distinguished.

```json
{
  "case_id": "leave-policy-001",
  "reviewer_id": "reviewer-1",
  "question": "How many annual leave days?",
  "answer": "Employees receive 20 days of annual leave.",
  "reference_answer": "20 days per year",
  "context": [
    "Employees receive 20 days of annual leave per year."
  ],
  "ratings": {
    "correctness": 5,
    "groundedness": 5,
    "citation_support": 4,
    "relevance": 5
  },
  "hallucination": false
}
```

Each case/reviewer pair must be unique. Every rating is an integer from 1
(poor) to 5 (excellent); the hallucination field is a separate reviewer
judgment, not inferred from the numeric ratings.

## Rating rubric

| Dimension | 1 | 3 | 5 |
|---|---|---|---|
| Correctness | Materially wrong | Partially correct or incomplete | Fully correct for the question |
| Groundedness | Unsupported by supplied context | Partly supported; includes uncertain claims | Every material claim is supported by context |
| Citation support | Citations missing or point to wrong evidence | Some claims are cited correctly | Citations support all material cited claims |
| Relevance | Does not answer the question | Partially answers or includes substantial noise | Directly answers without irrelevant content |

Use 2 and 4 for intermediate judgments. Mark `hallucination=true` when
the answer contains at least one material claim unsupported by the supplied
context. Do not mark a correct abstention as a hallucination.

Reviewers should see the same question, answer, reference answer, retrieved
context, and citation mapping. Blind reviewers to model/configuration where
practical. Sample both answerable and unanswerable questions; do not select
only successful examples. Keep the case set fixed when comparing configurations.

## Aggregate a review file

From the repository root:

```bash
.venv/bin/python -m backend.evaluation.human_review   artifacts/human-reviews/reviews.jsonl   --output artifacts/human-reviews/summary.json
```

The report includes mean ratings, positive (4–5) and low (1–2) rating rates,
reviewer-marked hallucination rate, review counts, and per-case rating ranges
when multiple reviewers score the same case. The script rejects malformed
records, invalid scores, and duplicate case/reviewer pairs.

## Interpretation limits

- The report describes only the cases and reviewers actually included.
- It does not calculate Cohen's kappa, Krippendorff's alpha, or another
  inter-rater reliability coefficient.
- A small or convenience-sampled review set is not representative of
  production traffic.
- Use identical cases, context, rubric, and sampling when comparing versions.
- Do not publish a human-review metric until real reviewers have completed
  the records. An empty template or an automated score is not human evidence.
