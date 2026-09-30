# Security

This document summarizes the security controls that are **actually implemented**
in NEXORA today, with where each lives in the code.

## Summary

| Area | Control | Status |
|------|---------|--------|
| Password storage | Argon2 (`pwdlib` recommended) | Implemented |
| Login timing | Constant-time (always one Argon2 verify, dummy hash for unknown users) | Implemented |
| Brute force | Per-email in-process throttle → 429 + `Retry-After` | Implemented |
| Access tokens | JWT HS256, `exp` required, 30-min default | Implemented |
| Refresh tokens | Random 32-byte, stored as SHA-256, rotated + revocable, 30-day default | Implemented |
| JWT secret strength | Prod startup rejects <32 chars or known-weak secrets | Implemented |
| CORS | Disabled unless configured; wildcard rejected in production | Implemented |
| Tenant isolation | Enforced at API, service, Postgres, and Qdrant layers + post-query re-check | Implemented |
| Upload validation | Size, content-type allowlist, **magic-byte** check | Implemented |
| Path traversal | Storage confined to base dir (`is_relative_to`) | Implemented |
| SQL injection | SQLAlchemy parameterized queries / ORM (no string-built SQL) | Implemented |
| Error leakage | Typed errors → static messages; generic 500 hides internals | Implemented |
| Audit logging | Append-only, allowlisted detail keys, request id attached | Implemented |
| Secret hygiene | `.env` untracked & git-ignored; no tracked secrets; provider keys never logged | Implemented |
| Prod config fail-fast | Missing LLM provider config in production blocks startup | Implemented |

## Passwords and login

- **Argon2** hashing; plaintext never stored.
- A precomputed **dummy hash** ensures login always does exactly one Argon2
  verification, so response time does not reveal whether an email is registered
  (no account enumeration).
- Failed login → throttle records a failure, `login.failure` audit event, and a
  uniform **401**. The throttle (`login_throttle.py`) is thread-safe, in-process,
  caps tracked emails at 10,000, and uses an injectable clock for tests. After
  `LOGIN_MAX_FAILED_ATTEMPTS` (5) it locks the email for `LOGIN_LOCKOUT_SECONDS`
  (300) and returns **429**.

## Tokens

- Access tokens are JWTs signed with `JWT_SECRET_KEY` (HS256). Decoding
  **requires** an `exp` claim.
- Refresh tokens are `secrets.token_urlsafe(32)`; only the **SHA-256 hash** is
  stored. Refresh **rotates** (old revoked, new issued); logout revokes.
- `get_current_user` returns the same 401 message for every failure mode.

## Production configuration validation

`validate_production_safety` runs at startup when `ENVIRONMENT=production`:

- `JWT_SECRET_KEY` must be ≥32 characters and not in the weak-secret list
  (which includes `changeme`, `nexora`, and the CI-only secret).
- CORS must not use a wildcard origin.
- The **active** LLM provider must be fully configured
  (`ollama` → `OLLAMA_MODEL`; `openai` → `OPENAI_API_KEY` + `OPENAI_MODEL`).

If any check fails, the application **refuses to start** rather than running in
an unsafe state.

## Tenant isolation (defense in depth)

1. Organization routes require a membership or an admin/owner role.
2. Services scope every lookup by `organization_id`.
3. Postgres repositories filter by `organization_id`.
4. Qdrant points carry `organization_id`; every `search` and `delete` filter
   **must** match it (deletes also match `document_id`). Integer payload indexes
   exist on `organization_id` and `document_id`.
5. After Qdrant returns candidate ids, chunks are re-fetched from Postgres
   **filtered by the same organization**, so a stray vector cannot leak another
   tenant's text.

See [multi-tenancy.md](multi-tenancy.md).

## Upload safety

- Size capped (`MAX_UPLOAD_SIZE_BYTES`, default 10 MiB); the body is streamed in
  1 MB chunks and rejected as soon as it exceeds the cap.
- Content-type allowlist: PDF and DOCX only.
- **Magic-byte** validation: PDF must begin `%PDF-`, DOCX must begin `PK`.
- Stored files are confined to `STORAGE_PATH`; `_resolve_within_base` +
  `is_relative_to` block path traversal.

## Injection

- **SQL:** all data access goes through the SQLAlchemy ORM / parameterized
  queries; there is no string-concatenated SQL.
- **Path:** handled by the storage guard above.

## Error handling and information leakage

- Typed domain exceptions map to specific statuses with **static** or
  non-sensitive messages (e.g. `LLMGenerationError` → 503 "LLM provider request
  failed"; the real reason is logged, not returned).
- A catch-all handler returns **500** `{"detail":"Internal server error"}` plus
  an `X-Request-ID` header and logs the exception server-side. Stack traces and
  internals never reach the client.

## Audit logging

- Actions recorded: login success/failure, document upload/version-replace/
  delete/status-change, membership add/role-change/remove, platform role change.
- **Detail allowlist:** `_SAFE_DETAIL_KEYS = {version, file_size, content_type,
  status, role, target_user_id}`. Anything else is dropped, so the audit log
  never contains passwords, tokens, request bodies, headers, prompts, or
  document content.
- Each event carries the request id (from the `ContextVar` set by middleware).
- Writing an audit event is **best-effort**: a failure is swallowed (with a
  rollback and a warning) so auditing can never break a primary operation.
- Reading audit logs requires org owner/admin.

## Logging and observability

- Request logging records **only** request id, method, path, status code, and
  duration — never headers, bodies, query strings, prompts, or answers.
- A client-supplied `X-Request-ID` is accepted only if ≤128 chars and matching
  `^[A-Za-z0-9._-]+$`; otherwise a UUID is generated (prevents log injection).
- The Docker entrypoint waits for Postgres and logs **only the exception class**
  on connection failure, never the connection URL (which could contain a
  password).

## Secrets in the repository

- `git ls-files | grep -E '(^|/)\.env($|\.)|secret|credential|\.pem$|\.key$'`
  matches only `.env.example` (a committed contract of placeholders — no real
  secret values).
- `.env` is git-ignored and **not tracked**.
- LLM provider API keys are never logged.
- Docker compose marks `POSTGRES_PASSWORD` and `JWT_SECRET_KEY` as required
  (`:?`) so the stack refuses to start without them.

## Dependency risk

- All dependencies are **pinned** to exact versions in `requirements.txt`
  (36 lines). CI installs from this file, so builds are reproducible.
- `torch` is a transitive dependency of `sentence-transformers` (not pinned
  directly).
- No known unused heavyweight frameworks (LangChain core / LangGraph were
  removed; Redis/Celery are not used).
- A full `pip-audit`/CVE sweep was **not run** in this pass — treat dependency
  vulnerability scanning as a recommended pre-production step (see
  [deployment-readiness.md](deployment-readiness.md)).

## Known limitations (honest)

- The login throttle is **per-process**. Behind multiple replicas it limits each
  replica independently (an attacker spreading attempts across replicas gets a
  higher combined budget). A shared store (e.g. Redis) would be needed for a
  global limit — deliberately out of scope for the modular monolith.
- No rate limiting beyond login throttling (e.g. per-IP API rate limits) is
  implemented.
- Dependency CVE scanning is not wired into CI.
