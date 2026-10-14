# Production Hardening & Verification Runbook

This document records what must be **measured or verified**, rather than assumed, before calling NEXORA production-ready.

## 1. CI verification

The CI workflow now covers four independent concerns:

- PostgreSQL-backed migrations, dataset validation, compilation, and tests.
- Python dependency vulnerability scanning with `pip-audit`.
- Production Compose configuration validation.
- Production Docker image build.

A green CI run proves the repository is internally consistent on the GitHub runner. It does **not** prove that a live Ollama-backed deployment is reachable from the public internet.

`pip-audit` is a dependency vulnerability scanner, not a source-code security analyzer. Keep that distinction explicit when interpreting its result.

## 2. Local production-stack verification

Run these commands on a machine with a working Docker daemon:

```bash
export POSTGRES_PASSWORD="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
export JWT_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"

docker compose -f docker-compose.prod.yml config -q
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d

docker compose -f docker-compose.prod.yml ps
curl -fsS http://127.0.0.1:8000/health
```

Then perform an authenticated smoke test:

1. Register a test user.
2. Log in and obtain an access token.
3. Create an organization.
4. Upload one supported PDF or DOCX document.
5. Wait for ingestion to reach `ready`.
6. Query the document.
7. Verify the answer contains citations.
8. Query an unanswerable question and verify refusal.
9. Verify a second organization cannot access the first organization's document.
10. Delete the test organization and confirm no benchmark/test data remains.

Do not mark the deployment verified until all ten steps succeed.

## 3. Latency measurement

NEXORA already reports retrieval, generation, TTFT, and total timings. The important next measurement is a distribution, not one lucky request.

Run the included bounded load test against a private/local deployment:

```bash
python scripts/load_test.py \
  --url http://127.0.0.1:8000/api/v1/organizations/<ORG_ID>/query \
  --token "$NEXORA_ACCESS_TOKEN" \
  --question "What is the annual leave policy?" \
  --requests 50 \
  --concurrency 10
```

Repeat at concurrency 1, 5, 10, 20, and 50 when the machine can safely handle it. Record:

- throughput (requests/sec)
- error rate
- median latency
- p95 latency
- p99 latency
- maximum latency

The script is intentionally standard-library-only and is a bounded measurement tool. It must not be used against systems you do not own or have permission to test.

## 4. Retrieval evaluation

The repository contains both the original policy corpus and a research-paper corpus. The evaluation dataset should be treated as a benchmark, not as proof of universal RAG quality.

Before publishing new benchmark numbers:

```bash
.venv/bin/python -m backend.evaluation.dataset
```

Then run the retrieval and answer benchmarks using a scratch database, Qdrant instance, and local Ollama model as documented in `docs/evaluation.md`.

Always report:

- corpus size
- number of positive cases
- number of negative cases
- Recall@1 / Recall@k
- MRR
- fact accuracy
- citation accuracy
- refusal rate
- latency distribution
- whether results are single-run or repeated

Do not describe a small benchmark as a production SLA.

## 5. Benchmark expansion policy

For the next benchmark revision, add cases in these categories where the corpus supports them:

- exact lookup
- paraphrase
- keyword-heavy query
- semantic query
- identifier/entity lookup
- distractor documents
- unanswerable questions
- conflicting or ambiguous wording
- multi-hop questions where the corpus genuinely requires more than one passage

Each new case must have an explicit ground-truth source and expected fact(s). Do not manufacture expected answers just to improve a metric.

## 6. Deployment limitations to keep visible

The following are legitimate single-node limitations and should not be hidden:

- local-disk uploads require shared/object storage for multi-replica deployment;
- per-process login throttling is not a global rate limiter;
- FastAPI `BackgroundTasks` is not a durable queue;
- public deployment needs dependency vulnerability scanning and regular updates;
- throughput/concurrency must be measured before making scaling claims;
- local Ollama latency is hardware/model dependent.

Only introduce Redis, object storage, a durable queue, or other infrastructure when a measured requirement justifies it.
