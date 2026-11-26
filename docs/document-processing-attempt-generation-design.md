> **Current-status notice (2026-11-26):** The live background worker is now integrated with attempt-owned generation staging, Qdrant generation writes, readiness-gated promotion, and active-generation retrieval. Several checkpoint paragraphs below explicitly say these pieces are not integrated; those statements are historical and were true at their checkpoint dates, not current. For the authoritative implementation/risk checklist, see [document-processing-lifecycle-current-status.md](document-processing-lifecycle-current-status.md). Cleanup/reconciliation and external-write fencing remain incomplete.


## Retry-safe failed generation cleanup

Cleanup now targets only a generation already marked failed and still owned by the current processing attempt. It rejects the active generation pointer, deletes Qdrant points using generation + document + tenant filters, verifies the exact remaining point count is zero, and only then deletes SQL generation chunks. The generation row remains as a failed audit record.

The cleanup operation is idempotent: repeating vector deletion and zero-count verification after SQL chunks have already been removed is safe. If vector deletion or verification fails, SQL chunk deletion is not performed. Caller still owns SQL transaction commit/rollback.

This primitive is not wired into the processing worker; stale-owner cleanup and recovery scheduling remain separate work.

# Document Processing Attempt Ownership: Safe Index Generation Design

## Status

Current implementation checkpoint for PR #23. The live background worker is integrated with attempt-owned generation processing, lease renewal, generation-scoped SQL chunks and Qdrant vectors, vector-index parity readiness, conditional promotion, and active-generation retrieval. This is not a cross-store transaction; automatic abandoned-generation cleanup remains intentionally disabled pending external-write fencing. The historical checkpoints below record the evolution of the design and should not be read as current status.

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

## Failed candidate retirement

The repository now has a narrowly scoped helper that marks a candidate generation failed only when the current processing owner/lease and generation metadata match. It does not delete chunks or Qdrant vectors and does not alter the active-generation pointer. Cleanup of candidate SQL/vector artifacts remains a separate operation that must be generation-scoped and safe to retry.

A regression test promotes a known-good generation, starts replacement staging, retires the failed replacement, and asserts the original generation remains active while the candidate is marked failed. This test exercises SQL lifecycle preservation only; vector cleanup is still not implemented or worker-integrated.

## Readiness-gated promotion primitive

A promotion wrapper now runs the fail-closed readiness check and calls the existing conditional SQL promotion only when staged SQL and exact generation-scoped Qdrant point counts match. Tests cover both rejected mismatch (document remains processing, generation remains staging) and accepted parity (document becomes ready and points to the candidate generation).

This remains a repository primitive, not live worker integration. There is no distributed transaction: callers must serialize generation writes and cleanup around readiness/promotion, and commit SQL only after the wrapper returns true. The previous active generation remains untouched by a rejected readiness check.

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

## Stale-attempt recovery and orphan-generation audit checkpoint

Stale document recovery now locks the document row, scopes the transition to the stale processing attempt, and changes that attempt's remaining `staging` generations to `abandoned` before clearing the document's owner token. Both single-document and startup/bulk recovery paths use the same scoped transition. Generations from other attempts and non-staging lifecycle states are not changed.

This transition is SQL-only and does not delete generation chunks or Qdrant points. An abandoned generation is cleanup-eligible metadata, not proof that cleanup succeeded. A future reconciliation worker must discover abandoned generations, re-check that the generation is not active, delete vectors with generation/document/tenant filters, verify zero vectors, and then remove SQL chunks. Recovery does not attempt external cleanup while invalidating ownership, because Qdrant operations cannot participate in the SQL transaction and a stale worker may still be completing an external write.

The single-document recovery path now locks its row and rechecks the stale predicate in the query itself, preventing it from resetting a document that became fresh between the initial observation and mutation. This is still conservative groundwork: worker heartbeat/lease renewal, external writes, and the reconciliation scheduler are not integrated end-to-end.


## Abandoned-generation discovery primitive

A repository query now lists abandoned generations that are not referenced by the document's active-generation pointer. It is bounded by a caller-supplied limit, deterministic by creation time and generation ID, and returns generation metadata only. Non-positive limits return an empty list.

This is discovery, not a cleanup claim or lease. It intentionally does not lock or mutate rows and does not perform vector/SQL deletion. Multiple future reconcilers may observe the same candidate. Before cleanup can be scheduled, it still needs a durable claim/lease and external-write fencing: a stale processing attempt must not be able to recreate vectors after the reconciler verifies deletion. Active-pointer exclusion is a guard, not a substitute for transactional claims or cleanup fencing.


## Cleanup concurrency and external-write fencing checkpoint

A durable cleanup claim is necessary but insufficient on its own. A lease can prevent two reconcilers from intentionally processing the same generation at once, but it cannot stop an expired processing worker from completing a delayed Qdrant upsert after cleanup has verified zero points. Deleting again on a retry is not a fencing guarantee if a late write can occur after the final retry.

Before automated abandoned-generation deletion is enabled, the worker/repository boundary must establish all of the following:

- generation-scoped vector writes are authorized only for the current attempt and staging generation;
- write authorization and cleanup are coordinated so an already-authorized external write cannot outlive the cleanup fence (a check immediately before an upsert is not sufficient by itself);
- cleanup claims are durable, bounded, conditional, and recoverable after lease expiry, and never target the active pointer;
- vector deletion is generation + document + organization scoped and followed by an exact zero-count check;
- SQL staged chunks are deleted only after vector verification succeeds, while lifecycle/audit metadata is retained;
- retries and claim expiry cannot permit two cleanup owners to mutate the same generation concurrently.

Until the external-write fencing design is proven and tested, this branch keeps abandoned-generation discovery read-only. Adding claim columns or a claim API now would create a misleading sense of safety without making vector deletion safe. The next implementation step is to design and test the fencing boundary around generation-scoped Qdrant writes, then add durable cleanup claims and reconciliation as a separate change.
