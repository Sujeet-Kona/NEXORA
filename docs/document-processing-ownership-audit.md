# Document processing ownership audit

**Audit date:** 2026-11-22  
**Branch:** `feat/document-processing-attempt-ownership`

## Scope

This audit checks whether the attempt-token and generation repository groundwork is
actually used by the live FastAPI background processing path.

## Findings

### Blocker: the live worker is still not fenced by an attempt token

`backend/services/document_processing_worker.py` calls
`process_document_background`, which performs stale recovery and then calls
`process_document` without an attempt token. The legacy
`backend/services/document_processing_service.py` transitions the document to
`PROCESSING`, persists document chunks, indexes document-scoped vectors, and
sets `READY` without validating that the worker still owns the processing
attempt.

The token-aware helpers in `backend/repositories/document_repository.py`
(`claim_document_processing_attempt`, lease renewal, owner checks, and
token-scoped finalization) and the staging-generation helpers in
`backend/repositories/document_generation_repository.py` are not connected to
this live processing path.

Consequently, timestamp-based recovery can reset a long-running worker's
document to `PENDING` after 30 minutes. A newer worker may then start while
the older worker continues external work. The old worker can still write
document-scoped vectors or perform best-effort cleanup; SQL row locks do not
fence those Qdrant operations.

### Blocker: generation staging and promotion are not end-to-end

The legacy worker still uses document-scoped chunk replacement and indexing.
Generation-scoped SQL staging and Qdrant operations exist, but live indexing,
active-generation retrieval, promotion, and retirement are not fully wired as
one controlled workflow. A generation's SQL state alone cannot make its
vectors atomically visible across PostgreSQL and Qdrant.

### Risk: cleanup crosses attempt boundaries in the legacy path

The legacy exception handler deletes all chunks and document-scoped Qdrant
vectors for a document. It does not prove that the failing worker remains the
current owner before cleanup. A stale worker could therefore erase newer
processing output if concurrency/recovery allows overlap.

## Required integration before claiming concurrency safety

1. Claim a processing attempt atomically before dispatching work; pass its token
   to the worker and all mutation/finalization calls.
2. Use lease expiration/renewal as the authoritative ownership mechanism;
   stale recovery must compare lease expiry and clear the owner conditionally.
3. Stage SQL chunks and Qdrant vectors under a generation identifier, never
   overwrite the active generation during processing.
4. Validate generation/vector parity and attempt ownership before promotion.
5. Fence or serialize Qdrant writes and cleanup so late operations from stale
   attempts cannot corrupt the active generation.
6. Make failure cleanup generation-scoped and conditional on ownership; do not
   delete document-wide artifacts from an unowned worker.
7. Make retrieval explicitly select the active generation, and test the old
   generation remains queryable until a successful promotion.
8. Add deterministic concurrency tests: stale worker resumes after recovery/new
   claim; delayed vector upsert after promotion; cleanup from an expired attempt;
   failed promotion leaves prior active generation intact.

## Verification status

Migration and schema constraints have been added with tests. The preflight tests
added in commit `01c8cc4` exercise safe rejection of inconsistent legacy rows.
CI run #311 passed on `9b7159c`; CI #312 is the current run for
`01c8cc4` and must be checked before treating the new tests as verified.

This audit is intentionally conservative: repository primitives and schema
constraints are useful groundwork, but they do not make the live worker
concurrency-safe until integration and concurrency tests are complete.
