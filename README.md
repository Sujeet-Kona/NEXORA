# Nexora

Secure Enterprise AI Knowledge Platform.

## Backend

Nexora currently provides a FastAPI backend with SQLAlchemy database support and a User API.

## Requirements

- Python 3.12+
- PostgreSQL

## Setup

Create and activate a virtual environment:

    python -m venv .venv
    .\.venv\Scripts\Activate.ps1

Install dependencies:

    python -m pip install -r requirements.txt

Create a .env file and configure:

    DATABASE_URL=postgresql+psycopg://username:password@localhost:5432/nexora

Do not commit .env.

## Run the API

    python -m uvicorn backend.main:app --reload

API: http://127.0.0.1:8000
Interactive documentation: http://127.0.0.1:8000/docs

## Endpoints

Health check:

    GET /health

Users:

    GET /users
    POST /users
    GET /users/{user_id}

## Run tests

    pytest -q

The current test suite uses an isolated SQLite in-memory database.

## Validate the backend

    python -m compileall .\backend
