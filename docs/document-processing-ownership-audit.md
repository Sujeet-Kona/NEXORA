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


## Write-barrier feasibility checkpoint

### Candidate: SQL document-row lock held across each Qdrant upsert batch

Remote source inspection confirms the current upsert repository is synchronous and uses Qdrant `wait=True`. The processing service renews the lease in a separate committed transaction before calling upsert; no document-row lock is held across the external call. The deletion service already obtains a tenant-scoped document row lock and holds its transaction across Qdrant purge and SQL delete. Stale recovery also locks the document row before resetting ownership.


A minimally invasive candidate protocol is therefore to acquire the same document row lock in the processing worker immediately before each external upsert batch, revalidate status/token/unexpired lease under that lock, perform the synchronous Qdrant write while retaining the lock, then commit/rollback to release it. Recovery and deletion must continue to acquire the same row lock. This would serialize the external write with recovery and deletion: if the write wins, cleanup waits and purges afterward; if deletion/recovery wins, the stale attempt's revalidation fails and it cannot start the write.

### Required caveats before implementation

- Holding a SQL row lock during network I/O increases lock duration and can block deletion/recovery. Upsert must have a bounded timeout; lock wait and request timeout behavior must be explicit.
- The protocol depends on every generation upsert path using the barrier, and recovery/deletion/version replacement using the same document row lock. Audit all writers before implementation.
- A process crash releases the database lock, but an external request could outlive its client timeout. This candidate is only sound if the Qdrant client call's return/error behavior is understood and the test can model an operation continuing after timeout. If an operation can continue after the lock is released, SQL locking alone remains insufficient; a stronger fence or delayed cleanup grace/verification is required.
- Do not hold a SQL transaction open across embedding generation—only the narrow upsert batch window.
- Deterministic regression test must block the upsert while the DB lock is held, attempt recovery/deletion from another session, then release the upsert and verify purge happens after it. Also test barrier acquisition after recovery/deletion and lease/token mismatch.

This is a feasibility proposal, not an implementation or proof. It appears less invasive than a distributed lock service, but timeout semantics and complete writer coverage must be proven first.

**Verification limitation:** remote source review only; no local tests or CI run.


## Qdrant timeout and writer-path review (checkpoint)

**Reviewed:** 2026-11-22 at PR head `58e08e3e4c4e7cc6230baa5c423786dfae92d657`.

### Findings

- The generation-vector write is centralized in `QdrantRepository.upsert_generation_chunks`; it validates generation UUIDs, chunk indexes, embedding dimensions, and single-document/tenant scope per batch, then calls synchronous `client.upsert(..., wait=True)`.
- The attempt-owned generation processing service is the observed production call site for this method. It batches upserts by `qdrant_upsert_batch_size` (default 32) and renews the processing lease before each batch. This renewal is committed preflight, not a lock held across the Qdrant request.
- Qdrant client construction does not explicitly configure a timeout or retry policy in this repository. Runtime dependency is pinned to `qdrant-client==1.19.0`. Therefore this source review cannot establish whether a timed-out request may continue server-side after the synchronous call returns/raises; the client/server timeout behavior must be verified against the pinned client and protocol.
- `wait=True` asks Qdrant to wait for the write operation to complete before acknowledging, but it does not by itself prove that a request abandoned by the client cannot complete later. Do not treat it as a fencing guarantee.
- Legacy `upsert_chunks` is a separate path for integer chunk IDs. The legacy processor remains in the codebase, so a barrier integration must not accidentally wrap only generation writes while leaving any active legacy write/delete path able to race. This review did not complete an exhaustive caller inventory because remote file retrieval was intermittently rejected; that inventory remains a prerequisite.

### Protocol decision

Do not implement a SQL row-lock barrier yet. Its basic ordering argument is useful, but client timeout/cancellation semantics are unknown and caller coverage is not complete. The next evidence-gathering step is to inspect the pinned qdrant-client 1.19.0 request timeout/cancellation behavior and complete a repository-wide writer/cleanup call-site inventory. Then design the barrier tests to model server-side completion after client timeout, not only a normally blocked synchronous call.


**Verification limitation:** source review only. CI on the current head was observed completed successfully; no local test execution was possible.


## Pinned Qdrant HTTP client timeout review

**Reviewed:** 2026-11-22; source tag `qdrant-client v1.19.0` (the project's pinned version).

### Source-confirmed details

- `QdrantClient` documents a default timeout of **5 seconds** for REST and gRPC when `timeout=None`; this repository constructs the client without a timeout override.
- The synchronous REST API client is backed by `httpx.Client`. Its request path calls `Client.send` and wraps transport exceptions in `ResponseHandlingException`; no automatic retry loop is visible in the reviewed `ApiClient.send` implementation.
- Point upsert API supports an explicit Qdrant operation timeout parameter, but the repository's `upsert_generation_chunks` call supplies only `collection_name`, `wait=True`, and `points`; no operation timeout is set.

### What these facts do **not** prove

The five-second client timeout bounds how long the client waits, not necessarily the server-side lifetime of a write that Qdrant already accepted. The source review cannot prove that a request which times out/disconnects is canceled server-side or cannot be applied later. Consequently, a SQL row-lock barrier held only until the client call returns remains an insufficiently proven fence against delayed writes. This is a protocol uncertainty, not a confirmed observed late-write incident.

### Next required test/design work

1. Build a controlled test around the transport boundary where the client request times out while a simulated server-side write remains pending, then completes after deletion/purge; assert the proposed protocol prevents or detects resurrection.
2. Complete the full writer inventory for both generation and legacy vector upsert paths and their deletion/cleanup paths. Remote source retrieval was intermittent during this audit, so coverage is not yet claimed.
3. Consider using explicit Qdrant operation timeout and ordering only after semantics are understood; neither should be treated as cross-store fencing on its own.

**Verification:** source inspection of the upstream `qdrant-client v1.19.0` code and the project's pinned dependency only; no tests executed.


## Vector writer and cleanup call-site inventory (checkpoint)

**Reviewed:** 2026-11-22 at branch head `fae87f6c4191382803f406f93fb15462b4a07b6a`. This inventory is based on remote source reads of the Qdrant repository and processing/indexing/service modules; it is a source-call-site inventory, not runtime tracing.


### Vector mutation entry points

- `QdrantRepository.upsert_generation_chunks`: generation UUID point IDs; generation payload; called from `document_generation_processing_service.process_document_generation` in batches after a lease-renewal preflight. This is the intended attempt-owned staging write path.
- `QdrantRepository.upsert_chunks`: legacy integer-ID point writes; called by `document_indexing_service.index_document_chunks`. That legacy indexer remains referenced by `document_processing_service.process_document`, so it is still a code path to account for rather than assume removed.
- `QdrantRepository.delete_document_chunks`: broad document vector cleanup; observed in document-processing failure cleanup and document deletion service.
- `QdrantRepository.delete_legacy_document_chunks`: intentionally filters out generation-tagged points, called from document version replacement service.
- `QdrantRepository.delete_generation_chunks`: generation-scoped cleanup API; separate from legacy document purge.

### Lifecycle interaction observations

- Generation processing uses staged generation SQL chunks and generation-scoped vectors before promotion; active generation selection is SQL-pointer based. Its lease renewals are preflight updates, not a lock held over vector writes.
- The legacy processing service/indexer still performs shared-vector deletion and legacy upserts. The worker's generation processing path does not by itself prove legacy processing is unreachable from all entry points.
- Document deletion currently performs a document-wide vector purge while the SQL document row is locked, then deletes the SQL document. A late external write can still be a concern where the writer was not serialized by that same row lock.
- Version replacement's legacy vector deletion is deliberately scoped to legacy vectors, so generation-tagged vectors are preserved by that path.

### Coverage boundary and next gate

This inventory identifies the mutation methods and source call sites found in the reviewed modules. It does **not** establish runtime reachability, complete background-task scheduling coverage, or that every mutation is serialized against deletion/recovery. Before any row-lock barrier implementation, map API/task entry points to both processing services and add an assertion/test that legacy processing cannot be scheduled for a document once generation ownership is claimed (or deliberately fence both paths).

**Verification:** remote GitHub source reads and static call-site inspection only; no local test or runtime execution.


## Upload scheduling path review (checkpoint)

Reviewed `backend/api/v1/documents.py`, `backend/services/document_processing_worker.py`, and both processing services at the current audit branch.

- New document upload and version upload routes both schedule `process_document_background` through FastAPI `BackgroundTasks`.
- That background function invokes stale-processing recovery, then calls `process_document_generation`; it does not call the legacy `process_document` service.
- The legacy processor/indexer remain present as Python modules and reachable through their direct function imports, but no route call to the legacy processor was observed in the reviewed document API module. This is limited evidence; repository-wide runtime reachability was not established.
- Consequently, generation attempt fencing is the visible upload scheduling path, while legacy indexing remains a mutation API requiring its own caller-coverage assessment before being treated as safely unreachable.

**Verification:** static source review of the API and worker files only; no runtime/test execution.


## Failed-generation cleanup lifecycle gap (confirmed source-level)

Reviewed `document_generation_repository.py` cleanup primitives and `document_generation_processing_service.py` failure finalization.

### Evidence

1. `retire_failed_staging_generation` transitions an owned staging generation to `failed` while the document is still PROCESSING and its attempt lease is valid.
2. The processing exception handler then calls `finalize_document_processing_attempt(... FAILED ...)`; the repository finalization path changes document state and clears the attempt ownership/lease (confirmed in the repository source review).
3. `cleanup_failed_generation_artifacts` only accepts generation status `failed`, but also requires the document to remain PROCESSING with the same current attempt token and a non-expired lease. After normal failure finalization, these preconditions no longer hold. The cleanup primitive is therefore not a post-failure cleanup path.
4. `list_abandoned_generation_cleanup_candidates` discovers only status `abandoned`; it does not discover `failed` generations. Its own docstring says discovery-only and no cleanup claim or external fencing exists.
5. Repository tree review did not find a generation cleanup/reconciliation worker or task module by matching cleanup/reconciler naming. This search is not proof of absence of all indirect scheduling.

### Conclusion

**Confirmed lifecycle gap:** failed candidate generations can retain SQL chunk rows and generation-scoped Qdrant vectors after the document attempt has been finalized, and the currently inspected cleanup primitive cannot clean them in that post-finalization state. The abandoned-candidate discovery API also does not cover failed rows. No cleanup worker was identified in this tree/source review.

This is artifact-retention/resource cleanup, not evidence that failed generations are exposed by retrieval: active-generation SQL pointer filters continue to exclude non-active generations.

### Safe remediation requirements (not implemented)

- Add a durable cleanup claim/state that is independent of the document's live processing attempt (e.g., generation cleanup ownership/lease), rather than reusing an expired processing token.
- Candidate discovery must include inactive `failed` and `abandoned` generations, tenant/document consistency, and exclude active pointers.
- Cleanup must re-check active-generation status under SQL lock/claim, delete Qdrant vectors scoped by generation/document/tenant, verify vector count zero, then delete SQL chunk rows; retain the generation record as cleaned/tombstone or delete it only under a clear retention policy.
- Make retries bounded and observable, and fence cleanup against late generation writes; a cleanup claim alone does not solve a stale upsert arriving after purge.
- Add tests for failure finalization clearing attempt token, cleanup candidate coverage, retries, active-generation exclusion, Qdrant delete/count failure, and delayed upsert after purge.

**Verification:** remote source inspection only; no tests executed. This finding is limited to the code paths reviewed.


## Failed-generation cleanup protocol design checkpoint (not implemented)

This checkpoint refines the already-confirmed post-finalization cleanup gap into a proposed state protocol, based on the current generation model/repository/service source review.


### Model constraints relevant to cleanup

- `DocumentProcessingGeneration` currently has generation ID, document ID, organization ID, attempt ID, status, and creation time. There is no independent cleanup lease/claim, retry counter, or cleanup timestamp.
- Generation and generation-chunk rows have document/organization ownership constraints and document-delete cascades. This is appropriate for SQL lifecycle cleanup, but a cleanup worker relying on the document join cannot discover artifacts after SQL document deletion; external Qdrant artifacts may still exist if a write was delayed after a purge.
- Existing candidate discovery is document-joined and status-filtered, so it covers only rows for existing documents with `abandoned` status. It does not cover `failed` candidates after attempt finalization.

### Proposed durable state machine

Keep processing status and cleanup status conceptually separate. A minimal cleanup state should be independently claimable, with states such as `pending`, `claimed`, `retry`, and `complete`; claim metadata should include a cleanup token, expiry, attempt counter, and last error (sanitized). A migration must add constraints/indexes only after checking existing rows. Candidate eligibility must be derived by tenant/document/generation and exclude the active pointer under a SQL lock. Failed and abandoned inactive generations should become eligible; active generations must never be cleaned.

Worker sequence:
1. Claim a bounded candidate in a short SQL transaction using a lease/token and row locking (skip locked where supported); commit claim.
2. Revalidate the generation/document/tenant relationship and active pointer immediately before vector cleanup. Do not hold SQL transactions during vector deletion/count network calls unless the lock strategy is explicitly justified and bounded.
3. Delete generation vectors using the exact generation/document/tenant filter, then verify count is zero. Any exception or nonzero count marks/retries cleanup and retains SQL chunks.
4. Delete SQL chunk rows only after vector absence is confirmed. Commit chunk removal and cleanup completion atomically, guarded by the cleanup token. Preserve the generation record as a cleaned tombstone unless retention rules explicitly authorize deleting it.
5. Make claim expiry/retry safe and observable; cap retries or use backoff without permanently hiding candidates. A stale cleanup claimant must not finalize another claimant's work.

### Required fencing before implementation

This protocol alone does **not** prevent a delayed generation upsert from arriving after the vector count check/purge. Existing deterministic point IDs are generation-scoped but do not prevent recreation. Cleanup must be paired with an external-write barrier/fence (or another verified Qdrant-side mechanism) that proves no accepted write can recreate the generation after cleanup's final delete. The previously reviewed SQL row-lock barrier remains a candidate, but its sufficiency is not established because a client timeout/disconnect may not prove remote cancellation. Do not implement the cleanup worker until that external write fence is selected and testable.

### Test gate

Before enabling worker behavior, add deterministic tests for: post-failure finalized attempts discoverable; abandoned candidates discoverable; active generation excluded; cross-tenant mismatch excluded; two concurrent claims cannot own one generation; expired claim recovery; vector-delete exception/nonzero count retains SQL chunks; successful count-zero cleanup deletes only scoped chunks; stale claimant cannot finalize; delayed upsert after purge is fenced; document deletion and cleanup interaction. Migration must be exercised against the current Alembic chain and representative preexisting rows.

**Verification:** static inspection of model and repository/service source via GitHub only. This is a design checkpoint; no source code or migrations changed and no local tests were run.
