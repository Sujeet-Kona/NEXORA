# Nexora

Secure Enterprise AI Knowledge Platform with hybrid search and ground citations.

## Backend

Nexora currently provides a FastAPI backend with SQLAlchemy database support,
JWT authentication, multi-tenant organizations and a document ingestion /
retrieval pipeline.

All application endpoints are versioned under `/api/v1`. `/health` is the only
unversioned endpoint.

## Requirements

- Python 3.12+
- PostgreSQL 17 (required)
- Qdrant (required for document processing and query endpoints)
- Ollama (required for the query endpoint)

PostgreSQL and Qdrant can be started with the bundled compose file (requires a
Docker installation), or provided by any other means:

    docker compose up -d

## Setup

Create and activate a virtual environment:

    python -m venv .venv
    .\.venv\Scripts\Activate.ps1

Install dependencies:

    python -m pip install -r requirements.txt

Create a `.env` file based on `.env.example` and configure at least:

    DATABASE_URL=postgresql+psycopg://username:password@localhost:5432/nexora
    JWT_SECRET_KEY=replace-with-a-secure-secret

Do not commit `.env`.

Apply database migrations:

    alembic upgrade head

## Run the API

    python -m uvicorn backend.main:app --reload

API: http://127.0.0.1:8000
Interactive documentation: http://127.0.0.1:8000/docs

Embedding models and vector-store clients are constructed lazily on first use,
so the API starts and `/health` responds without loading model weights or
contacting Qdrant. The third-party libraries behind them (torch,
transformers, sentence-transformers) are still imported at process import
time, which costs a few seconds at startup.

## Run with Docker (production)

A multi-stage `Dockerfile` builds a slim, non-root API image (uvicorn on port
8000). On startup the container waits for Postgres, applies `alembic upgrade
head`, then serves the app. `docker-compose.prod.yml` wires the API to
`postgres:17` and `qdrant`, with named volumes for database, vector and upload
storage.

Set the required variables in the environment or a `.env` file (never commit
secrets). `POSTGRES_PASSWORD` and `JWT_SECRET_KEY` are mandatory and the
compose file refuses to start without them:

    POSTGRES_PASSWORD=... JWT_SECRET_KEY=... docker compose -f docker-compose.prod.yml up -d --build

The API is published on `${API_PORT:-8000}`. Postgres and Qdrant are not
published to the host; they are reachable only on the internal compose network.

Ollama is expected on the Docker host. The compose default is
`http://host.docker.internal:11434` (mapped via `host-gateway`); override
`OLLAMA_BASE_URL` if your LLM runs elsewhere. Set migrations aside by passing
`RUN_MIGRATIONS=false` to the `api` service.

## Endpoints

Health check:

    GET /health

Authentication:

    POST /api/v1/auth/register
    POST /api/v1/auth/login
    POST /api/v1/auth/refresh
    POST /api/v1/auth/logout
    GET  /api/v1/auth/me

Users (admin only):

    GET   /api/v1/users
    GET   /api/v1/users/{user_id}
    PATCH /api/v1/users/{user_id}/role

Organizations:

    POST   /api/v1/organizations
    GET    /api/v1/organizations/{organization_id}/members
    POST   /api/v1/organizations/{organization_id}/members
    PATCH  /api/v1/organizations/{organization_id}/members/{user_id}
    DELETE /api/v1/organizations/{organization_id}/members/{user_id}

Documents:

    POST   /api/v1/organizations/{organization_id}/documents
    GET    /api/v1/organizations/{organization_id}/documents
    POST   /api/v1/organizations/{organization_id}/documents/upload
    GET    /api/v1/organizations/{organization_id}/documents/{document_id}
    PATCH  /api/v1/organizations/{organization_id}/documents/{document_id}
    DELETE /api/v1/organizations/{organization_id}/documents/{document_id}

Retrieval:

    POST /api/v1/organizations/{organization_id}/query

The user, member and document list endpoints are paginated: they accept
`limit` (1-200, default 50) and `offset` (default 0) query parameters and
return at most `limit` records ordered by ascending id.

## Retrieval and Qdrant

Document chunks are embedded with BGE-M3 and stored in a Qdrant collection.
Each point carries `organization_id`, `document_id`, `chunk_id` and
`chunk_index` payload metadata, and its point id equals the Postgres chunk id.

Every retrieval path filters by `organization_id` in Qdrant and re-checks the
returned chunk ids against Postgres for the same organization, so a vector can
never be returned to a tenant that does not own the underlying row.

The query endpoint accepts an optional `document_ids` list to restrict
retrieval to specific documents of the organization:

    POST /api/v1/organizations/{organization_id}/query

    {
      "question": "How many days of annual leave do employees receive?",
      "document_ids": [12, 15]
    }

Omitting `document_ids` searches every document of the organization; an empty
list is rejected with 422. The filter is applied to the dense (Qdrant) and the
lexical (BM25) stage, and the Postgres re-check applies it too, so chunks of
other documents never reach the reranker or the LLM.

Retrieval depth is configurable with environment variables:

    RETRIEVAL_TOP_K=2            # chunks returned to the LLM after reranking
    RETRIEVAL_DENSE_TOP_K=10     # Qdrant vector candidates
    RETRIEVAL_LEXICAL_TOP_K=10   # BM25 candidates
    RETRIEVAL_RERANK_TOP_K=8     # RRF-fused candidates sent to the cross-encoder

All four values must be >= 1; invalid values fail fast at startup.

The Qdrant collection is created lazily by
`QdrantRepository.ensure_collection` on the first write, and integer payload
indexes are created on `organization_id` and `document_id` for non-local
deployments. Deleting a document removes its vectors; deleting a single chunk
is scoped to its organization as well.

## Authentication

Protected endpoints expect a bearer access token:

    Authorization: Bearer <access_token>

Access tokens are signed JWTs. Passwords are hashed with Argon2. Platform
administrators (`role=admin`) can manage users; all other users are members and
can only access organizations they belong to.

An access token must carry an `exp` claim; tokens without one are rejected. Login
performs one password verification regardless of whether the submitted email is
registered, so failed logins do not reveal which accounts exist.

## Run tests

    pytest -q

The default test suite uses an isolated SQLite in-memory database and does not
require PostgreSQL or Qdrant.

Migration tests exercise real Alembic migrations against a PostgreSQL database.
They are skipped unless `TEST_DATABASE_URL` is set, and the database name must
contain `test` because the fixture drops and recreates all tables:

    TEST_DATABASE_URL=postgresql+psycopg://nexora:nexora@localhost:5432/nexora_test pytest -q tests/test_migrations.py

## Validate the backend

    python -m compileall backend
