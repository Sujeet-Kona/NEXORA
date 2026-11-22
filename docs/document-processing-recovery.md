# Document processing recovery

Document processing runs through FastAPI background tasks in the API process. A process
restart can therefore interrupt in-flight work. The current generation-based path
uses database attempt ownership and leases, but the work is still in-process rather
than a durable external queue.

## Generation processing lifecycle

- A worker claims a document processing attempt with an ownership token and lease.
- Candidate chunks and vectors are written under a generation-specific identifier;
  the prior active generation remains available while the candidate is built.
- Staging writes, lease renewals, readiness checks, and promotion are guarded by
  the current attempt ownership.
- Promotion updates the active-generation pointer and READY status in a SQL
  transaction. A stale attempt must not promote.
- On failure or lost ownership, the candidate is retired/abandoned where the
  ownership guard allows it. Candidate artifacts are intentionally retained when
  cleanup cannot be proven safe.

The generation-based worker is routed from the background worker. The legacy
processor and legacy vector/chunk path still exist in the repository; their
remaining reachability and cleanup behavior must be audited before claiming the
legacy path is fully removed.

## Stale-worker recovery

Recovery selects PROCESSING documents whose lease is expired, or whose lease is
NULL and whose updated timestamp is older than the fallback threshold. Recovery
locks document rows with `FOR UPDATE SKIP LOCKED`, abandons staging generations
associated with the stale attempt (while excluding the document's active
generation), and returns the document to PENDING while clearing the attempt and
lease fields.

The lease and attempt token protect SQL mutations and promotion. They do **not**
cancel an already-issued external Qdrant request. A request may be delayed or
accepted after a worker loses ownership, so lease expiration is not proof that
all external writes have quiesced.

## Abandoned-generation cleanup: not implemented

The repository can list abandoned generations as bounded cleanup candidates. It
does not currently implement a durable cleanup claim/lease, a cleanup
reconciler, or a completed lifecycle that deletes SQL chunks and verifies
generation-scoped Qdrant vectors.

Abandoned generation chunks and vectors can consequently accumulate. Active
generation retrieval is SQL-pointer scoped, so abandoned candidates are not
intended to be retrievable; the remaining concern is orphaned storage and
cross-store consistency.

A cleanup claim or one-time delete is **not sufficient fencing** for late
Qdrant writes. A worker's request may already be in flight when recovery
abandons its generation, and that write may complete after a cleanup delete.
Any future cleanup implementation must account for delayed writes and retries
(e.g. by retaining cleanup tombstones and repeating reconciliation under a
well-defined bounded/quiescence protocol). Until that protocol is proven and
tested, cleanup should not be described as race-free and abandoned artifacts
should not be deleted automatically.

## Current limitations

- Processing is in-process; it is not backed by a durable queue.
- PostgreSQL and Qdrant do not share a transaction.
- Attempt ownership and lease checks fence guarded SQL transitions, not external
  writes already issued to Qdrant.
- Automatic abandoned-generation cleanup and late-write reconciliation are missing.
- The legacy processor remains present and needs a reachability/compatibility audit.

These are explicit limitations, not claims of production-grade distributed
concurrency guarantees.
