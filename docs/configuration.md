# Configuration

NEXORA is configured through environment variables. Local development normally
uses a git-ignored `.env` file loaded by `backend/core/config.py` via
`pydantic-settings`.

The committed [`.env.example`](../.env.example) is the copy-paste template.
This document explains what each variable controls and which values are required.

## Configuration precedence

For settings supplied by `pydantic-settings`, the effective value comes from:

1. values supplied directly by the settings loader,
2. real environment variables,
3. `.env`,
4. the built-in default.

Unknown environment variables are ignored (`extra="ignore"`).

## Application

| Variable | Default | Purpose |
|---|---|---|
| `ENVIRONMENT` | `development` | One of `development`, `testing`, `staging`, `production`. Production enables fail-fast safety validation. |
| `CORS_ORIGINS` | empty | Comma-separated allowed browser origins. Empty disables CORS middleware. `*` is rejected in production. |
| `CORS_ALLOW_CREDENTIALS` | `true` | Whether CORS requests may include credentials. |

## Database

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | required | SQLAlchemy PostgreSQL URL, for example `postgresql+psycopg://user:password@host:5432/nexora`. |
| `TEST_DATABASE_URL` | unset | Used by migration tests. The database name must contain `test` because the test fixture recreates its schema. |

## Authentication

| Variable | Default | Purpose |
|---|---|---|
| `JWT_SECRET_KEY` | required | Secret used to sign access tokens. In production it must be at least 32 characters and must not be a known weak value. |
| `JWT_ALGORITHM` | `HS256` | Supported HMAC JWT algorithm: `HS256`, `HS384`, or `HS512`. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Access-token lifetime. |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `30` | Refresh-token lifetime. |
| `LOGIN_MAX_FAILED_ATTEMPTS` | `5` | Failed logins before temporary email lockout. |
| `LOGIN_LOCKOUT_SECONDS` | `300` | Lockout duration. |

## File storage

| Variable | Default | Purpose |
|---|---|---|
| `STORAGE_BACKEND` | `local` | Currently implemented backend: local filesystem. |
| `STORAGE_PATH` | `storage` | Root directory for uploaded files. Access is path-traversal guarded. |
| `MAX_UPLOAD_SIZE_BYTES` | `10485760` | Maximum upload size; default is 10 MiB. |

## Embeddings

| Variable | Default | Purpose |
|---|---|---|
| `EMBEDDING_MODEL` | `BAAI/bge-m3` | Sentence-transformers embedding model for document chunks and queries. |
| `EMBEDDING_DIMENSION` | `1024` | Vector dimension expected by the model and Qdrant collection. |
| `EMBEDDING_BATCH_SIZE` | `32` | Number of chunks embedded per batch. |
| `QDRANT_UPSERT_BATCH_SIZE` | `32` | Number of vectors upserted per Qdrant batch. |

## Qdrant

| Variable | Default | Purpose |
|---|---|---|
| `QDRANT_URL` | `http://localhost:6333` | Qdrant server URL. |
| `QDRANT_API_KEY` | unset | Optional API key for hosted Qdrant. |
| `QDRANT_COLLECTION` | `nexora_document_chunks` | Collection containing document-chunk vectors. |

## Retrieval

| Variable | Default | Purpose |
|---|---|---|
| `RETRIEVAL_TOP_K` | `2` | Final chunks passed to the LLM after reranking. |
| `RETRIEVAL_DENSE_TOP_K` | `10` | Dense/vector candidates retrieved from Qdrant. |
| `RETRIEVAL_LEXICAL_TOP_K` | `10` | BM25 candidates retrieved from the lexical index. |
| `RETRIEVAL_RERANK_TOP_K` | `8` | Fused candidates sent to the cross-encoder. |
| `RETRIEVAL_MIN_RELEVANCE` | `0.5` | Minimum reranker relevance score. If no candidate survives, the request takes the deterministic refusal path. |

All retrieval `*_TOP_K` values must be at least 1. Invalid values fail at startup.

## LLM provider

| Variable | Default | Purpose |
|---|---|---|
| `LLM_PROVIDER` | `ollama` | Selects `ollama` or `openai` provider implementation. |

### Ollama

| Variable | Default | Purpose |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL. |
| `OLLAMA_MODEL` | unset | Model name. The example uses `qwen3:8b`; required in production when Ollama is active. |
| `OLLAMA_TIMEOUT` | `300` | Request timeout in seconds. |
| `OLLAMA_NUM_PREDICT` | `256` | Maximum generated tokens. |
| `OLLAMA_THINK` | `false` | Controls Ollama reasoning/thinking mode. |

### OpenAI-compatible provider

| Variable | Default | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | unset | API key; required in production when this provider is active. |
| `OPENAI_MODEL` | unset | Model name; required in production when this provider is active. |
| `OPENAI_BASE_URL` | unset | Optional OpenAI-compatible gateway URL. |
| `OPENAI_TIMEOUT` | `120` | Request timeout in seconds. |
| `OPENAI_MAX_TOKENS` | `512` | Maximum generated tokens. |

## Production fail-fast rules

When `ENVIRONMENT=production`, startup rejects unsafe configuration:

- `JWT_SECRET_KEY` must be at least 32 characters and not a known placeholder.
- `CORS_ORIGINS` must not contain `*`.
- `LLM_PROVIDER=ollama` requires `OLLAMA_MODEL`.
- `LLM_PROVIDER=openai` requires both `OPENAI_API_KEY` and `OPENAI_MODEL`.

The application therefore fails during startup instead of waiting for a live
request to expose a missing security or LLM setting.

## Production Docker Compose variables

`docker-compose.prod.yml` additionally uses:

| Variable | Purpose |
|---|---|
| `POSTGRES_USER` | PostgreSQL username. |
| `POSTGRES_PASSWORD` | PostgreSQL password; required by the production compose file. |
| `POSTGRES_DB` | PostgreSQL database name. |
| `API_PORT` | Host port published for the API; default `8000`. |
| `RUN_MIGRATIONS` | Set to `false` to skip automatic `alembic upgrade head`; default is `true`. |

The production compose file supplies container-network URLs for PostgreSQL,
Qdrant, and the Ollama gateway. See [deployment.md](deployment.md).

## Secret hygiene

- Never commit `.env` or real secret values.
- Keep production secrets outside the repository.
- Do not reuse development credentials in production.
- Use a secure `--env-file` or a secret-management system for production.
- Audit logs use an allowlist and do not store passwords, tokens, request bodies,
  headers, prompts, or document contents.
