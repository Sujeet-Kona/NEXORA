# Configuration

All configuration comes from environment variables (or a `.env` file), loaded
by `backend/core/config.py` using `pydantic-settings`.

**Precedence:** values passed directly in code > real environment variables >
`.env` file > built-in defaults. Unknown variables are ignored
(`extra="ignore"`).

`.env` is git-ignored and is **not** tracked by git. `.env.example` is the
committed contract that documents every variable.

## Application

| Variable | Default | Meaning |
|----------|---------|---------|
| `ENVIRONMENT` | `development` | `development` or `production`. Production turns on fail-fast safety validation. |
| `CORS_ORIGINS` | *(empty)* | Comma-separated allowed origins. Empty disables CORS middleware entirely. A wildcard (`*`) is rejected in production. |

## Database

| Variable | Default | Meaning |
|----------|---------|---------|
| `DATABASE_URL` | *(none — required)* | SQLAlchemy URL, e.g. `postgresql+psycopg://user:pass@host:5432/nexora`. |
| `TEST_DATABASE_URL` | *(unset)* | Only used by migration tests. Name must contain `test`; that database is wiped and rebuilt. |

## Authentication & tokens

| Variable | Default | Meaning |
|----------|---------|---------|
| `JWT_SECRET_KEY` | *(none — required)* | Signing key for access tokens. In production must be ≥32 chars and not a known-weak value. |
| `JWT_ALGORITHM` | `HS256` | JWT signing algorithm. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Access-token lifetime. |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `30` | Refresh-token lifetime. |
| `LOGIN_MAX_FAILED_ATTEMPTS` | `5` | Failed logins before an email is temporarily locked. |
| `LOGIN_LOCKOUT_SECONDS` | `300` | Lockout duration once the threshold is hit. |

In production, `JWT_SECRET_KEY` is validated at startup: it must be at least 32
characters and must not appear in a built-in list of weak secrets (which
includes obvious values like `changeme` and the CI-only secret). A weak or short
secret makes the app refuse to start.

## Storage (uploaded files)

| Variable | Default | Meaning |
|----------|---------|---------|
| `STORAGE_BACKEND` | `local` | Storage backend. Only `local` (filesystem) is implemented. |
| `STORAGE_PATH` | `storage` | Base directory for uploaded files. Access is confined to this directory (path-traversal guard). |
| `MAX_UPLOAD_SIZE_BYTES` | `10485760` (10 MiB) | Maximum accepted upload size. |

## Vector store (Qdrant)

| Variable | Default | Meaning |
|----------|---------|---------|
| `QDRANT_URL` | `http://localhost:6333` | Qdrant server URL. |
| `QDRANT_API_KEY` | *(empty)* | Optional API key for hosted Qdrant (e.g. Qdrant Cloud). |
| `QDRANT_COLLECTION` | `nexora_document_chunks` | Collection name. Created lazily on first write. |

## Embeddings

| Variable | Default | Meaning |
|----------|---------|---------|
| `EMBEDDING_MODEL` | `BAAI/bge-m3` | Sentence-transformers model used to embed chunks and queries. |
| `EMBEDDING_DIMENSION` | `1024` | Vector dimensionality. Must match the model and the Qdrant collection. |
| `EMBEDDING_BATCH_SIZE` | `32` | Chunks embedded per batch during indexing. |
| `QDRANT_UPSERT_BATCH_SIZE` | `32` | Points upserted per batch. |

## Retrieval depth

| Variable | Default | Meaning |
|----------|---------|---------|
| `RETRIEVAL_TOP_K` | `2` | Chunks passed to the LLM after reranking. |
| `RETRIEVAL_DENSE_TOP_K` | `10` | Vector candidates pulled from Qdrant. |
| `RETRIEVAL_LEXICAL_TOP_K` | `10` | BM25 candidates. |
| `RETRIEVAL_RERANK_TOP_K` | `8` | RRF-fused candidates sent to the cross-encoder. |
| `RETRIEVAL_MIN_RELEVANCE` | `0.5` | Reranker relevance threshold. Chunks below it are dropped; if none survive, the system refuses to answer. |

All four `*_TOP_K` values must be ≥1; invalid values fail fast at startup.

## LLM provider

| Variable | Default | Meaning |
|----------|---------|---------|
| `LLM_PROVIDER` | `ollama` | `ollama` or `openai`. Selects the client in `backend/services/llm/provider.py`. |

### Ollama (default, local)

| Variable | Default | Meaning |
|----------|---------|---------|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL. |
| `OLLAMA_MODEL` | `qwen3:8b` | Model name. Required in production when provider is `ollama`. |
| `OLLAMA_TIMEOUT` | `300` | Request timeout in seconds. |
| `OLLAMA_NUM_PREDICT` | `256` | Max tokens generated. |
| `OLLAMA_THINK` | `false` | Disable the model's reasoning trace (keeps latency low). |

### OpenAI-compatible (optional)

| Variable | Default | Meaning |
|----------|---------|---------|
| `OPENAI_API_KEY` | *(empty)* | API key. Required in production when provider is `openai`. Never logged. |
| `OPENAI_MODEL` | *(empty)* | Model name. Required in production when provider is `openai`. |
| `OPENAI_BASE_URL` | *(empty)* | Optional gateway URL for OpenAI-compatible servers. |

### Production fail-fast

When `ENVIRONMENT=production`, startup validation (`validate_production_safety`)
requires the **active** provider to be fully configured:

- `LLM_PROVIDER=ollama` → `OLLAMA_MODEL` must be set.
- `LLM_PROVIDER=openai` → both `OPENAI_API_KEY` and `OPENAI_MODEL` must be set.

If the selected provider is missing required configuration, the application
refuses to start rather than failing later at request time.

## Production compose variables

`docker-compose.prod.yml` reads these (see [deployment.md](deployment.md)):

| Variable | Meaning |
|----------|---------|
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | Postgres credentials. `POSTGRES_PASSWORD` is **mandatory** (`:?` guard). |
| `JWT_SECRET_KEY` | **Mandatory** (`:?` guard). |
| `API_PORT` | Host port for the API (default `8000`). |
| `RUN_MIGRATIONS` | Set to `false` to skip `alembic upgrade head` on container start (default `true`). |

The compose file builds `DATABASE_URL` from the `POSTGRES_*` values and sets
`QDRANT_URL=http://qdrant:6333` and `OLLAMA_BASE_URL` (default
`http://host.docker.internal:11434`) internally.

## Secret hygiene

- Never commit `.env` or any secret value.
- `git ls-files` shows no tracked `.env`, `.pem`, `.key`, `secret`, or
  `credential` files.
- The audit log stores only an allowlisted set of detail keys and never tokens,
  passwords, request bodies, headers, prompts, or document content.
