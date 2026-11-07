# Deployment

This document covers how NEXORA is packaged and deployed, and the **verification
status** of each part as of 2026-11-07.

## Packaging artifacts

| File | Purpose |
|------|---------|
| `Dockerfile` | Multi-stage build → slim, non-root API image (uvicorn on 8000; readiness-based container healthcheck). |
| `docker-entrypoint.sh` | Waits for PostgreSQL and Qdrant, runs `alembic upgrade head`, then `exec`s the CMD. |
| `docker-compose.prod.yml` | Wires API + `postgres:17` + `qdrant:v1.19.1` with persistent database, vector, upload, and model-cache volumes. |
| `docker-compose.yml` | Dev-only: Postgres + Qdrant (no API). |
| `.dockerignore` | Keeps `.git`, `.venv`, `.env`, tests, caches, and `*.md` out of the image. |
| `.github/workflows/ci.yml` | CI: Postgres-only service, migrations, `pip-audit`, compileall, `pytest -q`. |

## The API image

- Base `python:3.12-slim`, `# syntax=docker/dockerfile:1`, multi-stage.
- **Builder** stage installs build-essential and pip-installs `requirements.txt`
  into a virtualenv at `/opt/venv`.
- **Runtime** stage copies the venv + `backend` + `alembic` + `alembic.ini` +
  entrypoint, creates a non-root system user `app`, sets `PYTHONUNBUFFERED=1`,
  `PYTHONDONTWRITEBYTECODE=1`, `STORAGE_PATH=/app/storage`, `chown`s the storage
  dir, and runs as `USER app`.
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
- **api** — `build: .`, image `nexora-api:latest`, persistent `api_storage` and
  `model_cache` volumes (Hugging Face model downloads survive container recreation),
  `depends_on` postgres (`service_healthy`) and qdrant (`service_started`);
  the API entrypoint waits for Qdrant readiness before migrations, `restart: unless-stopped`,
  `extra_hosts: host.docker.internal:host-gateway`, ports
  `${API_PORT:-8000}:8000`, named volume `api_storage`.

**Required variables** (compose uses `:?` so it refuses to start without them):
`POSTGRES_PASSWORD`, `JWT_SECRET_KEY`. `DATABASE_URL` is built from
`POSTGRES_*`; `QDRANT_URL=http://qdrant:6333`; `OLLAMA_BASE_URL` defaults to
`http://host.docker.internal:11434` (Ollama runs on the Docker host);
`OLLAMA_MODEL` defaults to `qwen3:8b`; `ENVIRONMENT` defaults to `production`.

Only the API port is published; Postgres and Qdrant are reachable **only** on
the internal compose network. The Ollama model is not bundled in the Compose stack. Install Ollama on the
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

## Start the production stack

Use an explicit production env file (see the **WARNING** above — a bare
`docker compose ... up` will silently pick up the dev `.env`):

```bash
docker compose --env-file /secure/path/prod.env \
  -f docker-compose.prod.yml up -d --build
```

If you pass secrets inline instead, you must also set `OLLAMA_BASE_URL`
explicitly, otherwise the dev `.env` value (`localhost:11434`) overrides the
compose default and generation fails inside the container:

```bash
POSTGRES_PASSWORD='...' \
JWT_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')" \
OLLAMA_BASE_URL='http://host.docker.internal:11434' \
  docker compose -f docker-compose.prod.yml up -d --build
```

Never commit these secrets. Generate a strong JWT secret, e.g.:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

To skip migrations on start: pass `RUN_MIGRATIONS=false` to the `api` service.

## Historical verification status (2026-09-28)

| Check | Command | Result |
|-------|---------|--------|
| Compose config valid + required-var guards | `docker compose -f docker-compose.prod.yml config -q` (with throwaway env) | **PASS** (validated offline) |
| Image build | `docker build -t nexora:deployment-check .` | **Not verified — Docker daemon unavailable** |
| Prod stack boot (Postgres→Qdrant→API→Alembic→health) | `docker compose ... up -d --build` then health check | **Not verified — Docker daemon unavailable** |

During that 2026-09-28 session, the Docker daemon would not come up
(`docker info` failed; only native Postgres/Qdrant/Ollama processes were
running). Per the project rule, missing verification was reported as **"Not
verified"** rather than assumed. The compose **configuration** was validated
offline and passed, and the required-variable guards (`POSTGRES_PASSWORD`,
`JWT_SECRET_KEY`) were confirmed to abort startup when unset.

### Follow-up status (2026-11-07)

Docker is now available for local development: the PostgreSQL 17 and Qdrant
1.19.1 development containers have been started and their health checks passed.
The production Docker image build and isolated `docker-compose.prod.yml` stack
have **not yet been verified**; complete the smoke-test procedure below before
claiming production-container verification.

### Exact commands to finish Docker verification

Run these once a Docker daemon is available. Use **safe local test
credentials** and an **isolated project name** so nothing shared is touched:

```bash
# 1. Build the image
docker build -t nexora:deployment-check .

# 2. Write throwaway creds to a git-ignored file (NEVER commit)
cat > .env.verify <<'EOF'
POSTGRES_USER=nexora
POSTGRES_PASSWORD=verify-only-local-pass
POSTGRES_DB=nexora
JWT_SECRET_KEY=verify-only-0123456789abcdefghijklmnopqrstuvwxyzABCDEF
API_PORT=8000
EOF

# 3. Boot an isolated stack
docker compose -p nexora_verify --env-file .env.verify \
  -f docker-compose.prod.yml up -d --build

# 4. Wait for health, then check
docker compose -p nexora_verify -f docker-compose.prod.yml ps
curl -fsS http://localhost:8000/health   # expect {"status":"ok"}

# 5. Inspect logs for secrets / leaks (should show none)
docker compose -p nexora_verify -f docker-compose.prod.yml logs api | grep -iE 'password|secret|token' || echo "no secrets in logs"

# 6. Authenticated smoke test
curl -fsS -X POST http://localhost:8000/api/v1/auth/register \
  -H 'content-type: application/json' \
  -d '{"email":"verify@example.com","full_name":"Verify","password":"verify-only-pass"}'

# 7. Tear down the isolated project only (removes its volumes)
docker compose -p nexora_verify --env-file .env.verify \
  -f docker-compose.prod.yml down -v
rm -f .env.verify
```

The `down -v` targets only the `nexora_verify` project, so no other volumes or
databases are affected.

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
  `/health/ready`, then tears down only its own volumes. It uses a dummy
  OpenAI-compatible configuration and does **not** call an external LLM or prove
  model quality; live inference still requires a deployment-host smoke test.

## Recommended production architecture

Keep NEXORA a **modular monolith**. A reasonable production topology:

- **1..N stateless API replicas** behind a load balancer / reverse proxy
  (TLS terminated at the proxy). Each replica lazily builds its own embedding /
  Qdrant / LLM singletons, so horizontal scaling is safe.
- **Managed or self-hosted PostgreSQL 17** with backups and a tested restore.
- **Qdrant** (self-hosted or Qdrant Cloud with `QDRANT_API_KEY`), persistent
  volume.
- **Ollama** (or an OpenAI-compatible gateway) on a GPU host; set
  `OLLAMA_BASE_URL` accordingly.
- **Object storage** for uploads if you scale beyond a single shared volume
  (only `local` storage is implemented today; a shared/persistent volume is
  required for multi-replica).

Caveats to resolve before real production traffic (see
[deployment-readiness.md](deployment-readiness.md)): the login throttle is
per-process (not shared across replicas), uploads use local disk storage, and
CI's `pip-audit` check covers the pinned `requirements.txt` dependencies only;
it does not scan the base image, operating-system packages, or the full deployed
runtime environment.
