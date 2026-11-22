# Document Processing Attempt Ownership: Safe Index Generation Design

## Status

Design checkpoint for PR #23. The ownership primitives and attempt-fenced SQL chunk replacement are groundwork only; the processing worker is not yet integrated. This document records the concurrency contract required before that integration.

## Current behavior and failure modes

- SQL `DocumentChunk` rows are replaced before embedding/indexing completes.
- Qdrant points use SQL chunk IDs as point IDs.
- `index_document_chunks` deletes all existing document vectors before embedding and upserting replacement batches.
- Retrieval hydrates dense hits from PostgreSQL and rejects chunks unless the owning document is `READY`.
- Processing failure deletes committed SQL chunks and best-effort deletes document vectors.

Consequences: during reprocessing, a document is not searchable while it is `PROCESSING`; a failure can remove the prior chunk set and vectors; partial vector batches can be written before failure; cleanup operates at document scope and is unsafe for a stale worker.

## Required invariants

1. Only the current processing attempt can promote a staged generation to active.
2. An attempt can write and delete only its own staging generation.
3. Readers see one committed active generation; staged or abandoned generations are never retrievable.
4. A failed or expired attempt must not delete the active generation.
5. SQL remains the authority for organization membership, document state, generation activation, and chunk text.
6. Vector point IDs must be generation-scoped, not reused SQL chunk IDs.
7. Promotion must be a conditional database operation guarded by the document's attempt token.
8. Cleanup is idempotent and scoped to a specific generation.
9. A document's active generation remains available until a replacement is successfully promoted (unless product semantics intentionally choose to make it unavailable).
10. Lease renewal, promotion, terminal status, and ownership clearing must be atomic and conditional.

## Proposed generation model

Introduce an opaque `index_generation_id` (UUID) per processing attempt and persist an active-generation pointer on the document or in a dedicated generation table. Prefer a dedicated generation table if lifecycle metadata, retries, auditing, and cleanup scheduling need to be recorded.

Each staged SQL chunk carries the generation ID. Each Qdrant point receives a generation-scoped point ID and payload containing organization ID, document ID, generation ID, chunk index, and (if needed) document version. The SQL chunk row ID must not be the Qdrant point ID for staged generations.

### Staging

1. Claim the document and receive an attempt UUID.
2. Create a staging generation associated with the attempt.
3. Extract and chunk; persist SQL chunks tagged with that generation.
4. Embed and upsert generation-scoped Qdrant points; do not delete active vectors.
5. Verify the staged chunk/vector counts and any required embedding/indexing invariants.
6. Promote via a conditional SQL transaction: document is still PROCESSING, attempt token matches, generation is staged, and staged data is complete. Set active-generation pointer and READY state in the same transaction; clear attempt lease/token.
7. After promotion, enqueue/perform idempotent cleanup of older generations. Cleanup is never allowed to delete the newly active generation.

### Retrieval

Dense retrieval must constrain organization and active generation. SQL hydration must join document/chunk/generation and filter by the active generation (and READY state, if READY remains the visibility gate). Lexical retrieval must likewise select chunks only from the active generation. A point from an inactive generation is discarded even if Qdrant returns it.

Generation filters need a Qdrant payload index if the collection/provider configuration requires it; indexing is an optimization, not an authorization boundary. SQL validation remains the final gate.

## Vector readiness validation checkpoint

A fail-closed repository helper now compares the count of tenant/document/generation-scoped SQL staging chunks against the exact Qdrant point count for the same scope. It rejects empty SQL staging, invalid/stale ownership or generation metadata, mismatched counts (including extra vectors), and vector-store errors.

The helper is intentionally **not called by promotion or the live worker**. Count equality is a readiness signal, not a cross-store atomic guarantee: vectors could change after validation and before SQL promotion. The eventual worker integration must control generation writes/cleanup for the duration of staging and promotion, and revalidate current attempt ownership in the promotion transaction. Qdrant and SQL cannot share one transaction, so failure recovery must retain the prior active generation and clean only the failed candidate.

## Promotion safety audit checkpoint

The repository primitives have been reviewed, but **promotion is not yet safe to use in the live worker**:

- `promote_staging_generation` verifies current attempt ownership (including lease expiry) and a non-empty SQL staging chunk set.
- It does **not** verify that the corresponding Qdrant generation points were fully written, or that the vector count matches the staged SQL chunk count.
- `upsert_generation_chunks` uses generation-scoped point IDs and `wait=True`, which avoids legacy point-ID collisions; however, a successful write call alone is not a durable readiness contract for promotion, and partial/failed external writes require scoped cleanup.
- SQL promotion updates the active-generation pointer in a transaction. Qdrant writes are external and cannot participate in that SQL transaction. A future integration must therefore stage vectors first, validate vector readiness, then perform conditional SQL promotion; on promotion failure, delete only the failed staging generation. If readiness cannot be established, do not promote.
- Existing generation repository tests exercise SQL ownership, staged chunks, stale promotion, and empty-generation rejection. They do not yet test vector-write failure/readiness against promotion, or preservation of a previously active generation during a failed replacement.

This checkpoint is an explicit guardrail: **the promotion helper must not be wired into the production processing path until vector readiness and failure-cleanup coordination are implemented and tested.**

## Failure and recovery

- Extraction or embedding failure: mark only the attempt/generation failed; retain active generation.
- Partial Qdrant writes: delete only staging generation point IDs/payloads; never document-wide delete.
- Lease expiry: recovery invalidates the attempt token and marks staging generation abandoned/cleanup eligible. A stale worker may finish external calls, but its generation is inactive and conditional promotion fails.
- Cleanup failure: record/retry cleanup separately; do not change the active generation.
- Promotion transaction failure: active pointer remains unchanged; cleanup staged generation later.
- Empty documents/chunk sets: explicitly define whether empty generation can be promoted (recommended: reject as empty, consistent with current extraction policy).

## Implementation order

1. Add generation schema and migration, with an active-generation pointer and attempt-to-generation relationship.
2. Add SQL generation-scoped chunk CRUD and retrieval.
3. Add Qdrant generation-scoped point IDs/payloads, upsert, search filters, and generation cleanup; keep existing legacy API during migration if tests require it.
4. Add a promotion transaction that verifies ownership and staged completeness.
5. Add fault-injection tests for partial embedding/upsert, lease expiry, stale promotion, cleanup failure, and preservation of the active generation.
6. Integrate the worker only after generation-scoped writes, promotion, retrieval filters, and failure cleanup are tested.
7. Remove or retire legacy document-wide vector deletion from the owned processing path.
8. Run full CI, inspect every job, then update PR readiness and documentation.

## Explicitly deferred

Do not enable attempt ownership in the existing processing worker while it still calls legacy document-wide chunk/vector replacement and cleanup. The token checks alone do not fence Qdrant operations or prevent an old worker from deleting shared points.
