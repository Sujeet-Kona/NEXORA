# Setup (local development)

This guide gets NEXORA running on your own machine for development. For
production-style deployment see [deployment.md](deployment.md).

## Prerequisites

- **Python 3.12+**
- **PostgreSQL 17** (required)
- **Qdrant** (required for document processing and the query endpoints)
- **Ollama** with the `qwen3:8b` model (required for the query endpoint)
- **Docker** (optional, the easiest way to run Postgres and Qdrant)

## 1. Clone and create a virtual environment

```bash
git clone https://github.com/Sujeet-Kona/NEXORA.git
cd NEXORA

python -m venv .venv
# macOS / Linux
source .venv/bin/activate
# Windows (PowerShell)
.\.venv\Scripts\Activate.ps1
```

## 2. Install dependencies

```bash
python -m pip install -r requirements.txt
```

All dependencies are pinned to exact versions in `requirements.txt`. Note that
`sentence-transformers` pulls in `torch`, which is a large download.

## 3. Start Postgres and Qdrant

The bundled development compose file starts **only** the data stores (Qdrant on
6333/6334 and Postgres 17 on 5432, credentials `nexora`/`nexora`/`nexora`):

```bash
docker compose up -d
```

You can also point NEXORA at any Postgres and Qdrant you already run by setting
`DATABASE_URL` and `QDRANT_URL`.

## 4. Start Ollama and pull the model

```bash
ollama serve          # if not already running as a service
ollama pull qwen3:8b
```

## 5. Configure environment

Copy the example file and edit it:

```bash
cp .env.example .env
```

The minimum you must set for local development:

```
DATABASE_URL=postgresql+psycopg://nexora:nexora@localhost:5432/nexora
JWT_SECRET_KEY=<a long random string>
```

`.env` is git-ignored — never commit it. See
[configuration.md](configuration.md) for every variable.

## 6. Apply database migrations

```bash
alembic upgrade head
```

The migration chain is linear with a single head (`c3d9a1f0e5b7`, 16 revision
files). Migrations are PostgreSQL-only.

## 7. Run the API

```bash
python -m uvicorn backend.main:app --reload
```

- API: http://127.0.0.1:8000
- Interactive docs (Swagger UI): http://127.0.0.1:8000/docs
- Health check: http://127.0.0.1:8000/health → `{"status":"ok"}`

### Startup behavior

Embedding models, the Qdrant client, and the LLM client are constructed
**lazily on first use**, so `/health` responds without loading model weights or
contacting Qdrant. The heavy libraries (torch, transformers,
sentence-transformers) are still imported at process start, which costs a few
seconds.

## 8. Run the tests

```bash
pytest -q
```

The default suite uses an **in-memory SQLite** database and does not require
Postgres, Qdrant, or Ollama (the LLM is faked). Migration tests are skipped
unless `TEST_DATABASE_URL` is set — see below.

### Migration tests against real Postgres

Migration tests exercise the real Alembic chain against PostgreSQL. They are
skipped unless `TEST_DATABASE_URL` is set, and the database name **must contain
`test`** because the fixture drops and recreates all tables:

```bash
TEST_DATABASE_URL=postgresql+psycopg://nexora:nexora@localhost:5432/nexora_test \
  pytest -q tests/test_migrations.py
```

## 9. Validate the backend compiles

```bash
python -m compileall backend
```

## A note on disabling Ollama "thinking"

`qwen3:8b` can emit an internal reasoning trace before answering, which adds
roughly 8–16 seconds per answer. NEXORA sets `OLLAMA_THINK=false` by default in
`.env` to disable it. Keep it disabled unless you specifically want the
reasoning trace and accept the latency.

## Troubleshooting

See [troubleshooting.md](troubleshooting.md) for common problems (port
mismatches, dead Docker daemon, slow first query, model not found).
