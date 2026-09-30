# Multi-tenancy

NEXORA is multi-tenant: many organizations (tenants) share one deployment, and
each tenant's data is strictly isolated from the others. This document explains
the data model and the isolation guarantees.

## The seven tables

| Table | Purpose |
|-------|---------|
| `users` | Platform accounts (email, Argon2 password hash, platform `role`, timestamps). |
| `refresh_tokens` | SHA-256 hashes of issued refresh tokens, with revocation and expiry. |
| `organizations` | Tenants (name, timestamps). |
| `organization_memberships` | Which user belongs to which organization, with an organization `role`. Unique on `(organization_id, user_id)`. |
| `documents` | Document metadata per organization (name, storage key, size, content type, page/word/character counts, status, failure reason, version). |
| `document_chunks` | Extracted chunk text per document, with `chunk_index` and page range (`page_start`, `page_end`). |
| `audit_logs` | Append-only audit trail (action, actor, organization, resource, request id, success, allowlisted details). Indexed on `(organization_id, created_at)`. |

### Enums

- `UserRole` (platform): `admin`, `member`.
- `OrganizationRole` (tenant): `owner`, `admin`, `member`.
- `DocumentStatus`: `pending`, `processing`, `ready`, `failed`.
- `AuditAction`: the ten values listed in
  [authentication.md](authentication.md).

## How a tenant is created

`POST /api/v1/organizations` (any authenticated user) creates an organization
and makes the caller its **owner**. The owner then adds members with roles.

## Isolation guarantees

Tenant isolation is enforced at **every** layer, not just one:

1. **API layer** — organization-scoped routes require a membership
   (`require_organization_member`) or an admin/owner role. No membership → 403.
2. **Service layer** — every document and query operation is passed the
   `organization_id` and looks data up **within** that organization.
3. **Postgres (repository) layer** — chunk and document queries filter by
   `organization_id`.
4. **Qdrant (vector) layer** — every point carries `organization_id` in its
   payload. Both `search` and `delete` build a filter that **must** match the
   caller's `organization_id` (and, for deletes, the `document_id`). Integer
   payload indexes on `organization_id` and `document_id` are created for
   non-local deployments.
5. **Post-query re-check** — after Qdrant returns candidate chunk ids, the
   retrieval service re-fetches those chunks **from Postgres filtered by the same
   organization**. Even if a stray vector were returned, a chunk belonging to
   another tenant would not hydrate and could never reach the reranker or the
   LLM.

The combination of "filter in Qdrant" **and** "re-check in Postgres" is the key
defense: the vector store is treated as an untrusted index, and Postgres remains
the source of truth for ownership.

## Document lifecycle and status transitions

Allowed transitions (enforced in `document_service.py`):

```
pending    → processing, failed
processing → ready, failed
ready      → (terminal — no further transitions)
failed     → pending   (allows a retry)
```

A `PATCH` that requests an illegal transition is rejected with **409**
(`InvalidDocumentStatusTransitionError`).

## Versioning

Documents carry an integer `version` (default 1). An admin/owner can replace a
document's content via `POST /organizations/{id}/documents/{doc_id}/versions`,
which **purges the old Qdrant vectors and chunks**, bumps the version, and
reprocesses the new content. This keeps the vector index consistent with the
current document.

## Deletion

Deleting a document (admin/owner, **204**) removes:

- its vectors from Qdrant (tenant- and document-scoped delete),
- its stored file from disk,
- its chunks and metadata row from Postgres,

and writes a `document.deleted` audit event.

## Cross-tenant test coverage

The test suite includes explicit cross-tenant isolation tests: a user from
organization A cannot read, query, or delete organization B's documents, and
vectors/chunks never leak across the boundary. These run in the default suite
(with fakes) and, where they touch Qdrant, in integration tests.
