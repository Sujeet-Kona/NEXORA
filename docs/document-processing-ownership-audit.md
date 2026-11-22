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
