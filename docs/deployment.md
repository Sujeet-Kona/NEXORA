# Deployment

This document covers how NEXORA is packaged and deployed, and the **verification
status** of each part as of 2026-09-28.

## Packaging artifacts

| File | Purpose |
|------|---------|
| `Dockerfile` | Multi-stage build → slim, non-root API image (uvicorn on 8000). |
| `docker-entrypoint.sh` | Waits for Postgres, runs `alembic upgrade head`, then `exec`s the CMD. |
| `docker-compose.prod.yml` | Wires API + `postgres:17` + `qdrant:v1.19.1` with named volumes. |
| `docker-compose.yml` | Dev-only: Postgres + Qdrant (no API). |
| `.dockerignore` | Keeps `.git`, `.venv`, `.env`, tests, caches, and `*.md` out of the image. |
| `.github/workflows/ci.yml` | CI: Postgres-only service, migrations, compileall, `pytest -q`. |

## The API image

- Base `python:3.12-slim`, `# syntax=docker/dockerfile:1`, multi-stage.
- **Builder** stage installs build-essential and pip-installs `requirements.txt`
  into a virtualenv at `/opt/venv`.
- **Runtime** stage copies the venv + `backend` + `alembic` + `alembic.ini` +
  entrypoint, creates a non-root system user `app`, sets `PYTHONUNBUFFERED=1`,
  `PYTHONDONTWRITEBYTECODE=1`, `STORAGE_PATH=/app/storage`, `chown`s the storage
  dir, and runs as `USER app`.
- `EXPOSE 8000`; `HEALTHCHECK` hits `http://127.0.0.1:8000/health` every 30s
  (timeout 5s, start-period 60s, 3 retries).
- `ENTRYPOINT ["./docker-entrypoint.sh"]`,
  `CMD ["uvicorn","backend.main:app","--host","0.0.0.0","--port","8000"]`.

## Entrypoint behavior

`docker-entrypoint.sh` (`set -e`):

1. Waits for Postgres with an inline Python loop (30 attempts × 2s). On failure
   it logs **only the exception class**, never the connection URL (which may
   contain the password).
2. If `RUN_MIGRATIONS` (default `true`) is `true`, runs `alembic upgrade head`.
3. `exec "$@"` (the CMD).

## Production compose

`docker-compose.prod.yml` defines three services:

- **postgres** — `postgres:17`, healthcheck `pg_isready`, named volume
  `postgres_storage`. Not published to the host.
- **qdrant** — `qdrant/qdrant:v1.19.1`, named volume `qdrant_storage`. Not
  published to the host.
- **api** — `build: .`, image `nexora-api:latest`, `depends_on` postgres
  (`service_healthy`) and qdrant (`service_started`), `restart: unless-stopped`,
  `extra_hosts: host.docker.internal:host-gateway`, ports
  `${API_PORT:-8000}:8000`, named volume `api_storage`.

**Required variables** (compose uses `:?` so it refuses to start without them):
`POSTGRES_PASSWORD`, `JWT_SECRET_KEY`. `DATABASE_URL` is built from
`POSTGRES_*`; `QDRANT_URL=http://qdrant:6333`; `OLLAMA_BASE_URL` defaults to
`http://host.docker.internal:11434` (Ollama runs on the Docker host);
`OLLAMA_MODEL` defaults to `qwen3:8b`; `ENVIRONMENT` defaults to `production`.

Only the API port is published; Postgres and Qdrant are reachable **only** on
the internal compose network.

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
# Production env file (never commit; store in your secret manager)
POSTGRES_USER=nexora
POSTGRES_PASSWORD=<strong, unique>
POSTGRES_DB=nexora
JWT_SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(48))")
OLLAMA_BASE_URL=http://host.docker.internal:11434   # or the GPU host address
ENVIRONMENT=production

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
  -f docker-compose.prod.yml config | grep -E 'JWT_SECRET_KEY|OLLAMA_BASE_URL'
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

## Verification status (2026-09-28)

| Check | Command | Result |
|-------|---------|--------|
| Compose config valid + required-var guards | `docker compose -f docker-compose.prod.yml config -q` (with throwaway env) | **PASS** (validated offline) |
| Image build | `docker build -t nexora:deployment-check .` | **Not verified — Docker daemon unavailable** |
| Prod stack boot (Postgres→Qdrant→API→Alembic→health) | `docker compose ... up -d --build` then health check | **Not verified — Docker daemon unavailable** |

The Docker daemon on this machine would not come up during this session
(`docker info` fails; only the native Postgres/Qdrant/Ollama processes are
running). Per the project rule, missing verification is reported as **"Not
verified"** rather than assumed. The compose **configuration** was validated
offline and passes, and the required-variable guards (`POSTGRES_PASSWORD`,
`JWT_SECRET_KEY`) were confirmed to abort startup when unset.

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
- Steps: checkout → setup-python 3.12 (pip cache) → install deps →
  `alembic upgrade head` → `python -m compileall -q backend` → `pytest -q`.

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
dependency CVE scanning is not in CI.
