# Document processing ownership and lifecycle audit

**Audit date:** 2026-11-22  
**Branch:** `feat/document-processing-attempt-ownership`  
**Scope:** Live background processing, attempt ownership, staging generations, promotion, retrieval, and failure/recovery behavior.

## Current implementation status

The live background worker is integrated with `process_document_generation`. It performs stale recovery, atomically claims a pending document with an attempt token and lease, creates a staging generation, stores generation-scoped SQL chunks, embeds and upserts generation-scoped Qdrant vectors, checks SQL/vector chunk-index parity, and conditionally promotes the candidate under the current attempt and lease. Retrieval has active-generation dense and lexical paths. The previous active generation is not replaced until successful promotion.

These protections are not a distributed transaction: PostgreSQL and Qdrant cannot commit atomically. External writes can outlive an attempt's lease. The branch deliberately retains failed/abandoned artifacts rather than automatically deleting them without external-write fencing.

## Verified lifecycle protections

- Attempt claims are conditional on `PENDING`; lease renewals and terminal finalization require the same token and an unexpired lease.
- Staging SQL and Qdrant artifacts are scoped to a generation, document, and tenant.
- Promotion requires current ownership, a nonempty SQL generation, and vector-index parity readiness.
- Dense and lexical active-generation retrieval are SQL active-pointer scoped.
- Stale recovery abandons only staging generations for the recovered attempt and does not delete Qdrant data.
- Failed candidate retirement does not alter the active pointer.
- Cleanup is scoped and verifies zero vectors before SQL chunk deletion, but the cleanup helper requires a current owner and is not an automated reconciler.

## Remaining risks and unfinished lifecycle work

1. **Cross-store atomicity:** readiness validation and SQL promotion cannot fence a delayed external Qdrant write by themselves.
2. **Cleanup orchestration:** failed/abandoned artifacts may accumulate. Cleanup discovery is read-only; no durable cleanup claim/reconciler is integrated.
3. **Lease-loss handling:** a worker that loses ownership returns without finalizing the newer attempt. Its staging artifacts rely on recovery/reconciliation, not immediate cleanup.
4. **Concurrency test coverage:** continue checking delayed external writes, recovery/new claim overlap, cleanup fencing, and preservation of an existing active generation under failure.

Do not enable automatic abandoned-generation deletion until the write/cleanup fencing boundary is proven. A durable cleanup lease alone is insufficient if a delayed vector write can arrive after deletion and verification.

## Verification notes

The PR branch had a successful CI run previously recorded at commit `3ad7a91611685cc345581940dea2a9b725919ea6`. This audit review did not execute local tests. Re-run CI on any documentation/code commit and inspect its result before considering that commit verified.


## Deletion lifecycle audit (checkpoint)

**Reviewed:** 2026-11-22 on the PR head at the time of this audit.

### Observed behavior

- The service obtains an organization-scoped document row lock and refuses deletion while the row is PROCESSING.
- Qdrant document-vector purge happens before SQL document deletion. The purge selector is scoped by both organization and document and includes generation vectors, not only legacy vectors.
- SQL document deletion commits separately. If the vector purge succeeds but the SQL delete/commit fails, the document row and local file can remain while its vector index has already been removed. The operation has no durable retry intent for this partial state.
- Local storage removal and audit-event recording happen after SQL deletion, so failures in those later steps are not atomic with the document deletion.
- Retrieval hydration and lexical/dense active-generation queries are SQL-tenant and active-pointer scoped, which limits stale vectors from becoming returned content. The listing endpoint currently returns documents regardless of processing status.

### Scope decision

Do **not** introduce a new document status solely for deletion in this checkpoint. DocumentStatus is consumed by processing claims, recovery, upload replacement, status-transition validation, retrieval readiness, API schemas, and tests; changing its enum would expand the migration and transition surface substantially. A dedicated durable deletion-intent record is a better next design candidate, but it must be specified before implementation.

### Required design and tests before changing behavior

1. Persist an idempotent, tenant/document-scoped deletion intent before external vector deletion; ensure processing claims and version replacement cannot race with the intent.
2. Make retrieval and document APIs consistently hide or report documents with an active deletion intent, without relying only on vector absence.
3. Reconcile the intent by retrying the scoped vector purge, then SQL deletion, then storage cleanup. Define audit behavior and intent retention for each failure point.
4. Test failures after intent commit, during Qdrant purge, after Qdrant succeeds but SQL deletion fails, and after SQL deletion succeeds but file cleanup fails. Retrying must not widen tenant/document scope or revive deleted content.
5. Separately address late vector writes from processing attempts: a purge-and-verify sequence is not a sufficient fence if a delayed Qdrant upsert can complete afterward. Deletion must serialize against/fence processing and external writes before claiming vector cleanup is final.

This is an audit/design checkpoint only. No deletion code or schema was changed in this commit, and CI was not run locally.


## Durable deletion-intent design (proposal, not implemented)

### Preferred data model

Use a dedicated `document_deletion_intents` table rather than adding `DELETING` to the existing document status enum. Keep one intent per `(organization_id, document_id)` pair. The intent must survive deletion of the document row, so avoid a cascading foreign key to `documents`; instead retain the immutable document ID and organization ID, and enforce uniqueness on the pair. Persist request actor, creation timestamp, and a small state (`pending_vectors`, `vectors_purged`, `sql_deleted`, `storage_pending`, `complete`) plus retry metadata. The intent is a durable workflow record; it must not contain document text, file contents, or credentials.


### Transaction and lock protocol

1. Begin SQL transaction and lock the document row with tenant scope.
2. Reject if the row is currently processing. Insert/ensure the deletion intent while holding the same row lock; commit. This commit is the durable deletion-request boundary.
3. Every document-processing claim and version-replacement mutation must lock the same document row and check for an intent before proceeding. A claim must be conditional so it cannot bypass the intent check.
4. Deletion reconciler claims intents using row locks/`SKIP LOCKED`, with bounded retry and observability. It must never rely on an in-memory queue as the source of truth.
5. Purge Qdrant by tenant + document + generation/legacy scope, then record the purge checkpoint transactionally. If that checkpoint fails, repeat the idempotent purge.
6. Delete the SQL document in a transaction and preserve intent state so retry can distinguish the missing document from an unrelated missing ID. File cleanup is retried from the durable intent's saved storage key; key must be treated as opaque and tenant-scoped. Only after storage cleanup and audit policy are satisfied is the intent marked complete or retained as a tombstone.

### Visibility contract

While an intent exists, retrieval hydration must exclude the document, lexical retrieval must exclude it, document detail/list APIs must not accidentally advertise it as normal, and processing/version replacement must refuse it. These checks should be SQL-backed; vector deletion is not the security boundary. Decide API behavior (404 vs explicit deleting state) before implementation and apply it consistently.

### Fencing limitation

The row-lock protocol fences database claims but cannot cancel an already-running Qdrant upsert. Before purge is considered final, external writes need a real fence: either a processing design that ensures every upsert is completed/acknowledged and ownership revalidated under a durable per-document write barrier that cleanup can acquire, or a point namespace/collection strategy where stale attempt writes are never visible and can be deterministically retired. Do not ship deletion reconciler as “safe” until a delayed-upsert-after-purge test demonstrates the fence.

### Retry semantics and failure matrix

- Intent commit fails: no external side effects; return failure.
- Qdrant purge fails: intent stays pending, document is hidden, worker/version changes blocked, retry continues.
- Qdrant purge succeeds but checkpoint commit fails: retry purge (idempotent).
- SQL document delete fails: intent persists; repeat purge and SQL delete.
- SQL delete succeeds but file delete fails: intent retains storage key and cleanup retries; no document resurrection.
- Audit fails: deletion workflow must not roll back an already committed external purge or SQL delete; define durable audit/outbox semantics explicitly before implementation.

### Exit criteria

The design is not implementation-ready until migrations and ownership constraints are reviewed, all read/claim/update paths are enumerated, and concurrency tests cover claim-vs-intent, replacement-vs-intent, retrieval during deletion, retry idempotency, and delayed vector writes after cleanup.


## External Qdrant write-fence review (checkpoint)

**Reviewed:** 2026-11-22 at PR head `d459685816815b002332b2afe5344916bf3fb4cf`.

### Confirmed write/cleanup ordering

- The generation processor renews the SQL attempt lease immediately before each Qdrant upsert batch, then calls the repository upsert. Lease renewal is a preflight check; it does not cancel or fence a request that is already in flight in Qdrant.
- Qdrant generation point IDs are deterministic within a generation (generation UUID + chunk index), and vectors carry tenant, document, and generation scope. Active-generation retrieval is SQL-pointer constrained, so a delayed write from an abandoned generation should not become visible merely by arriving late.
- Document deletion currently purges all vectors for tenant/document, then separately deletes the SQL document row. A stale worker may already have passed lease renewal and still have an upsert request in flight when recovery makes the document PENDING and deletion becomes allowed. The deletion purge can finish first; the delayed upsert can then repopulate vectors for the deleted document. SQL hydration prevents those vectors from becoming returned content, but this leaves orphaned external data and means vector purge is not a final cleanup guarantee.

### Concurrency timeline to reproduce

1. Worker A renews its attempt lease and submits a generation upsert; the request is delayed before Qdrant applies it.
2. A's lease expires and recovery abandons the generation and resets the document to PENDING.
3. A deletion request locks the now-non-PROCESSING document, purges tenant/document vectors, and deletes the SQL document.
4. The delayed Qdrant upsert from A completes after the purge.

This sequence is not prevented by SQL row locks because the external request already passed its SQL ownership check. It is a stale-write-after-purge race, not a retrieval disclosure demonstrated by this audit.

### Decision

No safe small code change was identified from the remote review alone. Adding another lease check after the upsert cannot undo a write that completed after deletion, and deleting abandoned generation vectors automatically would have the same race. Keep cleanup conservative. Before implementation, add a deterministic test with a blocked Qdrant upsert and explicit recovery/deletion ordering; then implement an external-write barrier or a visibility/namespace design that makes late writes non-visible and retireable. The deletion-intent protocol must coordinate with this fence rather than treating the SQL intent alone as cancellation.

**Verification limitation:** reviewed GitHub source only; no local test execution or CI run for this checkpoint.
