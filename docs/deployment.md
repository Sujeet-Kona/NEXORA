# Deployment

This document covers how NEXORA is packaged and deployed, and the **verification
status** of each part as of 2026-11-07.

## Packaging artifacts

| File | Purpose |
|------|---------|
| `Dockerfile` | Multi-stage build → slim, non-root API image (uvicorn on 8000; readiness-based container healthcheck). |
| `docker-entrypoint.sh` | Waits for PostgreSQL and Qdrant, runs `alembic upgrade head`, then `exec`s the CMD. |
| `docker-compose.prod.yml` | Wires API + `postgres:17` + `qdrant:v1.19.1` with project-scoped container names and persistent database, vector, upload, and model-cache volumes. |
| `docker-compose.yml` | Dev-only: Postgres + Qdrant (no API). |
| `.dockerignore` | Keeps `.git`, `.venv`, `.env`, tests, caches, and `*.md` out of the image. |
| `.github/workflows/ci.yml` | CI: migrations, `pip-audit`, compileall, `pytest -q`, Compose validation, and a production-container smoke test. |

## The API image

- Base `python:3.12-slim`, `# syntax=docker/dockerfile:1`, multi-stage.
- **Builder** stage installs build-essential and pip-installs `requirements.txt`
  into a virtualenv at `/opt/venv`.
- **Runtime** stage copies the venv + `backend` + `alembic` + `alembic.ini` +
  entrypoint, creates a non-root system user `app`, sets `PYTHONUNBUFFERED=1`,
  `PYTHONDONTWRITEBYTECODE=1`, `STORAGE_PATH=/app/storage`, `HF_HOME=/app/model-cache`,
  creates and `chown`s both persistent directories, and runs as `USER app`.
- `EXPOSE 8000`; `HEALTHCHECK` hits `http://127.0.0.1:8000/health/ready` every 30s
  (timeout 5s, start-period 60s, 3 retries).
- `ENTRYPOINT ["./docker-entrypoint.sh"]`,
  `CMD ["uvicorn","backend.main:app","--host","0.0.0.0","--port","8000"]`.

## Entrypoint behavior

`docker-entrypoint.sh` (`set -e`):

1. Waits for PostgreSQL with an inline Python loop (30 attempts × 2s). On failure
   it logs **only the exception class**, never the connection URL (which may
   contain the password).
2. Waits for the configured Qdrant endpoint with `qdrant-client` (60 attempts × 2s),
   including API-key authentication when configured. It logs exception classes only.
3. If `RUN_MIGRATIONS` (default `true`) is `true`, runs `alembic upgrade head`.
4. `exec "$@"` (the CMD).

## Production compose

`docker-compose.prod.yml` defines three services:

- **postgres** — `postgres:17`, healthcheck `pg_isready`, named volume
  `postgres_storage`. Not published to the host.
- **qdrant** — `qdrant/qdrant:v1.19.1`, named volume `qdrant_storage`. Not
  published to the host. The API entrypoint retries connectivity before migrations
  and server startup; this avoids depending on curl/wget inside the minimal Qdrant image.
- **api** — `build: .`, image `${NEXORA_IMAGE:-nexora-api:latest}`, Compose-project-scoped
  container names (no fixed `container_name`), persistent `api_storage` and
  `model_cache` volumes (Hugging Face model downloads survive container recreation),
  `depends_on` postgres (`service_healthy`) and qdrant (`service_started`);
  the API entrypoint waits for Qdrant readiness before migrations, `restart: unless-stopped`,
  `extra_hosts: host.docker.internal:host-gateway`, ports
  `${API_BIND_ADDRESS:-127.0.0.1}:${API_PORT:-8000}:8000`, named volumes
  `api_storage` and `model_cache`. The API binds to loopback on the host by default;
  put a TLS reverse proxy in front of it rather than exposing port 8000 publicly.

**Required variables** (compose uses `:?` so it refuses to start without them):
`POSTGRES_PASSWORD`, `JWT_SECRET_KEY`. `DATABASE_URL` is built from
`POSTGRES_*`; `QDRANT_URL=http://qdrant:6333`; `OLLAMA_BASE_URL` defaults to
`http://host.docker.internal:11434` (Ollama runs on the Docker host);
`OLLAMA_MODEL` defaults to `qwen3:8b`; `LOG_LEVEL`, embedding settings, and
Ollama generation settings are forwarded from the production env file;
`ENVIRONMENT` defaults to `production`.

Only the API port is published, bound to host loopback by default; Postgres and
Qdrant are reachable **only** on the internal compose network. Configure a host
reverse proxy with TLS and point it to `127.0.0.1:${API_PORT:-8000}`. The Ollama model is not bundled in the Compose stack. Install Ollama on the
configured inference host and pull the configured model before accepting RAG
traffic, for example `ollama pull qwen3:8b` (use the exact value of
`OLLAMA_MODEL`). Verify that `OLLAMA_BASE_URL` is reachable from the API
container. The Hugging Face embedding and cross-encoder artifacts are downloaded on first use
and cached under `HF_HOME=/app/model-cache`; the named `model_cache` volume keeps
them across API container replacement. First use still requires outbound access
to the Hugging Face Hub unless the cache is pre-populated.

The API's `/health` and `/health/live` endpoints
are liveness probes; `/health/ready` executes a lightweight PostgreSQL query and
checks Qdrant connectivity, returning HTTP 503 when either dependency is down.
The container healthcheck uses readiness, not liveness.

### WARNING: `docker compose` auto-loads the repo `.env` (dev-only)

`docker compose` **automatically reads a file named `.env` from the project
directory** and uses it to fill every `${VAR}` / `${VAR:-default}` in the
compose file. This repository ships a **development** `.env` (git-ignored) whose
values are unsafe for production but *silently pass* the startup guards:

- `JWT_SECRET_KEY` in the dev `.env` is a 43-character random string. It is
  **not** on the `WEAK_JWT_SECRETS` list and is `>= 32` chars, so the
  production safety check in `backend/core/config.py` **accepts it**. If prod
  boots with the dev secret, tokens are signed with a key that lives in a
  developer's working copy — a real credential-exposure risk, with no error.
- `OLLAMA_BASE_URL=http://localhost:11434` in the dev `.env` **overrides** the
  compose default of `http://host.docker.internal:11434`. Inside the API
  container `localhost` is the container itself, so generation calls fail at
  runtime even though the stack starts and `/health` returns `ok`.

**Therefore, for production you must supply an explicit env file and must not
let the dev `.env` be picked up.** Always deploy with `--env-file` pointing at a
production file (kept outside the repo, or a git-ignored `prod.env`), and
generate a **fresh** `JWT_SECRET_KEY` for each environment:

```bash
# Create a protected env file. Generate URL-safe DB credentials and a fresh JWT key.
umask 077
POSTGRES_PASSWORD="$(python -c 'import secrets; print(secrets.token_hex(32))')"
JWT_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
cat > /secure/path/prod.env <<EOF
POSTGRES_USER=nexora
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
POSTGRES_DB=nexora
JWT_SECRET_KEY=$JWT_SECRET_KEY
OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_MODEL=qwen3:8b
ENVIRONMENT=production
EOF
unset POSTGRES_PASSWORD JWT_SECRET_KEY

docker compose --env-file /secure/path/prod.env \
  -f docker-compose.prod.yml up -d --build
```

`--env-file` **replaces** the implicit `.env` lookup, so the dev file is not
read. If you cannot use `--env-file`, export the variables in the shell instead
(shell environment takes precedence over `.env`), or remove/rename the dev
`.env` on the deploy host. Verify what compose actually resolved before
starting:

```bash
docker compose --env-file /secure/path/prod.env \
  -f docker-compose.prod.yml config --quiet
```

## Start and verify the production stack

Use a dedicated, git-ignored verification env file. This avoids the repository's
development .env and uses fresh random secrets. The API binds to host loopback
on port 18001 so it does not collide with a development API on port 8000.

```bash
cd ~/NEXORA
umask 077
POSTGRES_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
JWT_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
cat > .env.verify <<EOF
POSTGRES_USER=nexora
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
POSTGRES_DB=nexora
JWT_SECRET_KEY=$JWT_SECRET_KEY
OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_MODEL=qwen3:8b
LLM_PROVIDER=ollama
ENVIRONMENT=production
API_PORT=18001
API_BIND_ADDRESS=127.0.0.1
LOG_LEVEL=INFO
EOF
unset POSTGRES_PASSWORD JWT_SECRET_KEY

docker compose -p nexora_verify --env-file .env.verify \\
  -f docker-compose.prod.yml config --quiet

docker compose -p nexora_verify --env-file .env.verify \\
  -f docker-compose.prod.yml up -d --build

docker compose -p nexora_verify --env-file .env.verify \\
  -f docker-compose.prod.yml ps

curl --fail --silent http://127.0.0.1:18001/health/ready
```

The first ingestion downloads the Hugging Face embedding and reranker models
unless the model-cache volume is already populated. The API container must be
able to reach the configured Ollama endpoint. On Docker Desktop for Mac,
host.docker.internal points back to the Mac; verify Ollama is running and that
the configured OLLAMA_MODEL has been pulled. If Ollama runs on another host,
replace OLLAMA_BASE_URL with that host's reachable URL.

Follow logs with the same env file and project name:

```bash
docker compose -p nexora_verify --env-file .env.verify \\
  -f docker-compose.prod.yml logs -f api
```

To stop the verification stack while preserving its database, uploaded files,
Qdrant data, and model cache:

```bash
docker compose -p nexora_verify --env-file .env.verify \\
  -f docker-compose.prod.yml down
```

Only when you intentionally want to erase this isolated verification data and
redownload models, add -v to down. Never use down -v against a real deployment
unless deleting all persisted application data is intended.

## Verification status

The historical 2026-09-28 local Docker-daemon limitation is superseded by the
current GitHub Actions container smoke test. The current CI run successfully
built the production image, started PostgreSQL and Qdrant, applied migrations,
passed /health/ready, and completed registration, login, authenticated profile,
refresh-token rotation, and logout.

This verifies the container packaging and core API startup path. It does not
verify real Ollama inference, document upload/processing, retrieval quality,
answer citations, SSE, public TLS, backups, or disaster recovery. Those require
the real-model smoke test below on the target host.
 
## Real model and document smoke test

After the stack is running and Ollama is reachable from the API container, run
the checked-in end-to-end smoke script from the repository root. It registers
(or logs in) a dedicated test user, creates a temporary organization, uploads
LORA.pdf, waits for the document to become READY, then exercises title/authors,
rank-four, equation, negative/refusal, and SSE queries. It prints source page
provenance and timing; inspect the generated answers rather than treating HTTP
200 as proof of answer quality.

```bash
export NEXORA_EMAIL='your-smoke-user@example.com'
read -s NEXORA_PASSWORD
export NEXORA_PASSWORD
.venv/bin/python scripts/smoke_test_live_deployment.py \\
  --base-url http://127.0.0.1:18001 \\
  --pdf benchmark-data/LORA.pdf
unset NEXORA_PASSWORD
```

The script intentionally leaves its test organization and uploaded document in
the local stack so the result can be inspected through the API. Delete that
organization/document using the normal authenticated API after reviewing it.

## CI pipeline

`.github/workflows/ci.yml` runs on push to `main` and on pull requests:

- Service container: **`postgres:17` only** (no Qdrant, no Ollama — tests use
  fakes/in-memory for those).
- Env: `DATABASE_URL` and `TEST_DATABASE_URL` (name contains `test`), a
  CI-only insecure `JWT_SECRET_KEY`, `JWT_ALGORITHM=HS256`,
  `STORAGE_BACKEND=local`, `STORAGE_PATH=storage`. `ENVIRONMENT` is **not** set
  (so it defaults to development and prod fail-fast is not triggered).
- Test job: checkout → setup-python 3.12 → install deps → production Compose
  config validation → `alembic upgrade head` → `pip-audit -r requirements.txt`
  → byte-compile → `pytest -q`.
- Separate `container-smoke` job builds the actual API image, starts the isolated
  production Compose stack with PostgreSQL and Qdrant, waits for migrations and
  `/health/ready`, then verifies registration, login, profile, refresh-token
  rotation, and logout before tearing down only its own volumes. It uses a dummy
  OpenAI-compatible configuration and does **not** call an external LLM or prove
  model quality; document ingestion and live inference still require a deployment-host smoke test.

## Recommended production architecture

Keep NEXORA a **modular monolith**. A reasonable production topology:

- **One API replica for the current implementation**, behind a host reverse
  proxy with TLS termination. Do not horizontally scale this version yet:
  BM25 indexes and login-throttle state are process-local, uploads use local
  filesystem storage, and ingestion uses in-process background tasks. Multiple
  replicas require shared BM25 invalidation/cache, shared rate limiting, shared
  object storage, and a durable job queue before they are safe.
- **Managed or self-hosted PostgreSQL 17** with backups and a tested restore.
- **Qdrant** (self-hosted or Qdrant Cloud with `QDRANT_API_KEY`), persistent
  volume.
- **Ollama** (or an OpenAI-compatible gateway) on a GPU host; set
  `OLLAMA_BASE_URL` accordingly.
- **Persistent local volume** for uploads for a single API replica. Object
  storage is not implemented in the current codebase; add it before multi-replica
  deployment rather than assuming a shared volume alone solves all state issues.

Caveats to resolve before real production traffic (see
[deployment-readiness.md](deployment-readiness.md)): the login throttle is
per-process (not shared across replicas), uploads use local disk storage, and
CI's `pip-audit` check covers the pinned `requirements.txt` dependencies only;
it does not scan the base image, operating-system packages, or the full deployed
runtime environment.
