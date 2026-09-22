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

## Authentication

Protected endpoints expect a bearer access token:

    Authorization: Bearer <access_token>

Access tokens are signed JWTs. Passwords are hashed with Argon2. Platform
administrators (`role=admin`) can manage users; all other users are members and
can only access organizations they belong to.

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
