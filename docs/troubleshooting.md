# Troubleshooting

Common problems and how to diagnose them, based on how NEXORA actually behaves.

## The API starts but queries fail

**Symptom:** `/health` returns `{"status":"ok"}` but `/query` errors.

`/health` deliberately does **not** touch Postgres, Qdrant, or the LLM. Heavy
clients are built lazily on first use, so a healthy `/health` does not prove the
data stores are reachable. Check each:

```bash
# Postgres
pg_isready -h localhost -p 5432        # or 5433, depending on your setup
# Qdrant
curl -fsS http://localhost:6333/healthz
# Ollama + model
curl -fsS http://localhost:11434/api/tags | grep qwen3:8b
```

## `DATABASE_URL` port mismatch

A frequent local issue: `.env` points at `:5432` but Postgres is actually on
`:5433` (or vice versa). Symptom: connection refused / timeout on any DB
operation. Verify the port your Postgres listens on and make `DATABASE_URL`
match. Environment variables override `.env`, so you can test with:

```bash
DATABASE_URL=postgresql+psycopg://nexora:nexora@localhost:5433/nexora \
  python -m uvicorn backend.main:app
```

## App refuses to start in production

`validate_production_safety` fails fast when `ENVIRONMENT=production` and:

- `JWT_SECRET_KEY` is shorter than 32 chars or is a known-weak value → set a
  long random secret: `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
- CORS is configured with a wildcard `*` → list explicit origins in
  `CORS_ORIGINS`, or leave it empty to disable CORS.
- The active LLM provider is under-configured → for `ollama` set `OLLAMA_MODEL`;
  for `openai` set both `OPENAI_API_KEY` and `OPENAI_MODEL`.

The startup error names the failing check. Fix the variable; do not weaken the
validation.

## `docker compose ... up` aborts immediately

`POSTGRES_PASSWORD` and `JWT_SECRET_KEY` are required with `:?` guards. If
either is unset, compose refuses to start and prints which variable is missing.
Provide them via the environment or a git-ignored `--env-file`.

## Docker daemon won't start (macOS)

**Symptom:** `docker info` fails; `Cannot connect to the Docker daemon`.

This is an environment problem, not a NEXORA bug. Non-destructive checks:

```bash
open -a Docker                 # launch Docker Desktop
docker info                    # poll until it responds
ls -l "$HOME/.docker/run/docker.sock"
export DOCKER_HOST="unix://$HOME/.docker/run/docker.sock"
export PATH="$HOME/.docker/bin:$PATH"
```

Do **not** delete Docker volumes or reset the VM to "fix" it — that destroys
data. If the daemon stays down, you can still run NEXORA natively: Postgres,
Qdrant, and Ollama can each run as host processes (as they did during this
audit), and the API runs with `uvicorn` directly.

## First query is very slow

The first query after process start loads the embedding model and reranker
weights (one-time). Subsequent queries reuse the cached singletons. Also, if
`OLLAMA_THINK=true`, `qwen3:8b` emits a reasoning trace that adds ~8–16s per
answer — keep `OLLAMA_THINK=false` unless you want it.

## Every answer is a refusal

**Symptom:** "The available documents do not contain enough information…".

This is the grounding guard firing because **zero** chunks cleared
`RETRIEVAL_MIN_RELEVANCE` (default 0.5). Causes:

- The relevant documents are not `ready` yet (still `processing` or `failed`) —
  check the document status and `failure_reason`.
- The corpus genuinely does not contain the answer (correct behavior).
- The threshold is too strict for your data — lower `RETRIEVAL_MIN_RELEVANCE`
  cautiously (too low risks ungrounded answers).

## A document is stuck in `failed`

Check `failure_reason` on the document:

- "Document contains no extractable text" — the file is image-only/scanned
  (NEXORA has **no OCR**) or otherwise has no extractable text.
- "Document text extraction failed" — unsupported format (only PDF and DOCX are
  supported) or a corrupt file.
- "Document processing failed" — a generic downstream error; check server logs
  with the request id.

You can retry by moving it back to `pending` (the `failed → pending` transition
is allowed).

## Upload rejected with 400

`InvalidDocumentUploadError` causes: empty filename, empty content, size over
`MAX_UPLOAD_SIZE_BYTES` (default 10 MiB), disallowed content type (only PDF and
DOCX), or magic bytes that do not match the declared type (PDF must start
`%PDF-`, DOCX must start `PK`). A renamed non-PDF/DOCX file will fail the magic
-byte check.

## Login returns 429

The per-email login throttle locked the account after
`LOGIN_MAX_FAILED_ATTEMPTS` (5) failures. Wait `LOGIN_LOCKOUT_SECONDS` (300) or
restart the process (the throttle is in-process). The response includes a
`Retry-After` header.

## Migration tests are skipped

`tests/test_migrations.py` skips unless `TEST_DATABASE_URL` is set, and the
database name **must contain `test`** (the fixture drops and recreates all
tables). Run:

```bash
TEST_DATABASE_URL=postgresql+psycopg://nexora:nexora@localhost:5432/nexora_test \
  pytest -q tests/test_migrations.py
```

## Qdrant collection dimension mismatch

If you change `EMBEDDING_MODEL` or `EMBEDDING_DIMENSION` after a collection
exists, upserts fail a dimension check. The collection is created with
`EMBEDDING_DIMENSION` (1024 for BGE-M3). Use a fresh `QDRANT_COLLECTION` name
(or recreate the collection) when changing embedding config, then re-index.

## Where to look in logs

Request logs include the `X-Request-ID`, method, path, status, and duration —
never bodies or secrets. Use the request id returned in the `X-Request-ID`
response header (on 500s) to correlate a client error with the server-side
`logger.exception` entry.
