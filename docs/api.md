# API Reference

Base URL: all application endpoints are versioned under **`/api/v1`**. `/health`
is the only unversioned endpoint.

Authentication: protected endpoints require `Authorization: Bearer
<access_token>`. See [authentication.md](authentication.md).

Pagination: the user, member, and document **list** endpoints accept `limit`
(1–200, default 50) and `offset` (default 0) query parameters and return at most
`limit` records ordered by ascending id.

## Health

| Method | Path | Auth | Response |
|--------|------|------|----------|
| GET | `/health` | none | `200 {"status":"ok"}` (does not touch the DB) |

## Auth

| Method | Path | Auth | Request | Response |
|--------|------|------|---------|----------|
| POST | `/api/v1/auth/register` | public | `{ email, full_name (1–255), password (8–128) }` | `201` `UserResponse` |
| POST | `/api/v1/auth/login` | public (throttled) | `{ email, password }` | `200` `TokenResponse` |
| POST | `/api/v1/auth/refresh` | refresh token | `{ refresh_token }` | `200` `TokenResponse` (rotates) |
| POST | `/api/v1/auth/logout` | refresh token | `{ refresh_token }` | `204` |
| GET | `/api/v1/auth/me` | bearer | — | `200` `UserResponse` |

`TokenResponse`: `{ access_token, refresh_token, token_type: "bearer" }`.

## Users (platform admin only)

| Method | Path | Request | Response |
|--------|------|---------|----------|
| GET | `/api/v1/users` | — | `200` list of `UserResponse` (paginated) |
| GET | `/api/v1/users/{user_id}` | — | `200` `UserResponse` |
| PATCH | `/api/v1/users/{user_id}/role` | `{ role }` (`admin`/`member`) | `200` `UserResponse` |

`UserResponse`: `{ id, email, full_name, role, created_at }`.

## Organizations

| Method | Path | Auth | Request | Response |
|--------|------|------|---------|----------|
| POST | `/api/v1/organizations` | bearer | `{ name (1–255) }` | `201` `OrganizationResponse` (creator becomes owner) |
| POST | `/api/v1/organizations/{id}/members` | org admin/owner | `{ user_id (>0), role }` | `201` `OrganizationMemberResponse` |
| GET | `/api/v1/organizations/{id}/members` | org member | — | `200` list (paginated) |
| PATCH | `/api/v1/organizations/{id}/members/{user_id}` | org admin/owner | `{ role }` | `200` `OrganizationMemberResponse` |
| DELETE | `/api/v1/organizations/{id}/members/{user_id}` | org admin/owner | — | `204` |

`OrganizationResponse`: `{ id, name, created_at }`.
`OrganizationMemberResponse`: `{ id, organization_id, user_id, role, created_at }`.
Organization roles: `owner`, `admin`, `member` (the `owner` role cannot be
assigned or reassigned by others).

## Documents

All under `/api/v1/organizations/{id}/documents`.

| Method | Path | Auth | Request | Response |
|--------|------|------|---------|----------|
| POST | `/documents` | org member | `{ name (1–255) }` | `201` `DocumentResponse` (metadata only, status `pending`) |
| POST | `/documents/upload` | org member | multipart file | `201` `DocumentResponse` (queued for background processing) |
| POST | `/documents/{doc_id}/versions` | org admin/owner | multipart file | `201` `DocumentResponse` (purges old vectors/chunks, bumps version, reprocesses) |
| GET | `/documents` | org member | — | `200` list (paginated) |
| GET | `/documents/{doc_id}` | org member | — | `200` `DocumentResponse` |
| PATCH | `/documents/{doc_id}` | org admin/owner | `{ status }` | `200` `DocumentResponse` (lifecycle guard) |
| DELETE | `/documents/{doc_id}` | org admin/owner | — | `204` (purges vectors + stored file) |

`DocumentResponse`:
```json
{
  "id": 1, "organization_id": 1, "uploaded_by": 1, "name": "policy.pdf",
  "storage_key": "...", "file_size": 12345, "content_type": "application/pdf",
  "page_count": 3, "word_count": 900, "character_count": 5400,
  "status": "ready", "failure_reason": null, "version": 1,
  "created_at": "...", "updated_at": "..."
}
```

Status values: `pending`, `processing`, `ready`, `failed`. Allowed transitions:
`pending→{processing,failed}`, `processing→{ready,failed}`, `ready→{}`,
`failed→{pending}`. An illegal transition returns **409**.

Upload limits: ≤ `MAX_UPLOAD_SIZE_BYTES` (default 10 MiB), content type must be
PDF or DOCX, and magic bytes must match (`%PDF-` / `PK`). See
[document-ingestion.md](document-ingestion.md).

## RAG query

| Method | Path | Auth | Request | Response |
|--------|------|------|---------|----------|
| POST | `/api/v1/organizations/{id}/query` | org member | `RAGQueryRequest` | `200` `RAGQueryResponse` |
| POST | `/api/v1/organizations/{id}/query/stream` | org member | `RAGQueryRequest` | SSE stream |

`RAGQueryRequest`: `{ question (min length 1), document_ids?: list[int] }`.
`document_ids` is optional; if present it must be non-empty (an empty list →
**422**).

`RAGQueryResponse`: `{ answer, sources: [ { citation_index, chunk_id,
document_id, document_name, chunk_index, score, page_start, page_end } ] }`.

Streaming (`/query/stream`) emits `text/event-stream`: `token` deltas, then a
terminal `done` event (`{ answer, sources, timing: { ttft_ms, total_ms } }`) or
an `error` event.

## Audit logs

| Method | Path | Auth | Response |
|--------|------|------|----------|
| GET | `/api/v1/organizations/{id}/audit-logs` | org **owner/admin** only | `200` list of `AuditLogResponse` (paginated) |

A plain member gets **403**. `AuditLogResponse`: `{ id, organization_id,
actor_user_id, action, resource_type, resource_id, request_id, success, details,
created_at }`. `details` contains only allowlisted keys (see
[security.md](security.md)).

## Error model

Errors return `{ "detail": "<message>" }` plus, for 500s, an `X-Request-ID`
header. Domain errors map to specific statuses:

| Status | When |
|--------|------|
| 400 | Invalid user id, invalid document upload |
| 401 | Invalid/expired credentials or token |
| 403 | Missing membership, insufficient role, admin-only route |
| 404 | User / organization / document not found |
| 409 | Conflict (duplicate user, duplicate membership, illegal status transition) |
| 422 | Pydantic validation (e.g. empty `document_ids`) |
| 429 | Too many login attempts (`Retry-After` header set) |
| 500 | Internal error (static "Internal server error"), LLM not configured |
| 503 | Document deletion failed, LLM provider request failed |

Generic 500s never leak stack traces or internals — only a static message and
the request id.

## Interactive docs

With the API running, Swagger UI is at `http://127.0.0.1:8000/docs` and ReDoc at
`http://127.0.0.1:8000/redoc`.
