# NEXORA document-processing lifecycle: current status

**Reviewed:** 2026-11-28  
**PR:** [#23](https://github.com/Sujeet-Kona/NEXORA/pull/23)  
**Branch:** `feat/document-processing-attempt-ownership`  
**Source head at review:** `a4289fa9d4e2991811004146c6474c77f33130fd`

This document is the current-status reference for the generation-based document lifecycle. Older design checkpoints in `document-processing-attempt-generation-design.md` are historical and must not be treated as the present implementation.

## Implemented path (verified from source)

- The API background worker routes processing through `process_document_generation`, not the legacy `process_document` pipeline.
- A pending document is claimed with an attempt token and expiring lease. Guarded SQL writes, lease renewal, failure finalization, and promotion require current ownership.
- Each attempt stages generation-specific SQL chunks and Qdrant vectors. Generation vector point IDs are UUID-derived and generation-scoped; staging does not intentionally delete the previous active index.
- Readiness validates the SQL chunk indexes against the generation-scoped Qdrant chunk indexes. Promotion is conditional on ownership and activates the new generation and `READY` state in a SQL transaction.
- Dense and lexical retrieval use the SQL active-generation pointer. Dense hits are hydrated from active SQL chunks; SQL is the authority for returned text and tenant scope. Dense hit payloads are now checked for generation, tenant/document scope, a non-boolean nonnegative chunk index, and the deterministic UUID5 point ID before hydration.
- Stale recovery returns an expired `PROCESSING` document to `PENDING`, clears the attempt token/lease, and marks that attempt's staging generations abandoned. Recovery does not delete vectors.
- Failed candidates can be marked failed without changing the active pointer.
- The legacy processor now uses an atomic `PENDING` claim and refuses documents with an active-generation pointer, generation history, or processing attempt/lease metadata. A focused regression test covers an abandoned generation; CI is pending for this change.

## Lifecycle checklist

| Area | Status | Evidence / limitation |
|---|---|---|
| Attempt claim / lease | Implemented | Conditional `PENDING` claim; token-guarded renew/finalize |
| Generation-isolated staging | Implemented | SQL chunk and Qdrant point IDs/payloads scoped by generation |
| Active-generation retrieval | Implemented | Dense and lexical SQL active-pointer filters |
| Promotion readiness | Implemented | SQL chunk indexes must match exact Qdrant generation indexes before conditional promotion |
| Dense hit identity validation | CI verified on `bcc175d0` (Run #401) | Reject malformed or mismatched Qdrant payload scope/index/point ID before SQL hydration; focused regression test added |
| Stale attempt recovery | Implemented | SQL-only recovery; does not cancel already-issued Qdrant requests |
| Failed candidate cleanup | Primitive only | Delete-and-count helper exists, but late writes can race; not automated |
| Abandoned-generation reconciler | **Missing** | Discovery only; no durable claim/retry/terminal cleanup |
| Late Qdrant write fence | **Unproven / missing** | Lease preflight is not cancellation for an in-flight request |
| Durable deletion intent / retry | **Missing** | Current deletion spans Qdrant, SQL, and local storage without a persisted workflow intent |
| Legacy processor isolation | Code/test committed; CI pending | Atomic `PENDING` claim; refuses active-generation pointers, generation history, and attempt/lease metadata; regression test added |
| Legacy path | **Still present** | Used by benchmark/evaluation code; generation-managed documents are blocked, but legacy work has no attempt lease or external-write fence |
| Cross-store atomicity | **Unavailable** | PostgreSQL and Qdrant do not share a transaction |
| Durable work queue | **Missing** | Processing is an in-process FastAPI background task |

## Confirmed cleanup and deletion hazards

1. **Generation cleanup race:** a generation-scoped Qdrant delete followed by a zero-count check is not final if an earlier upsert can still complete afterward. The cleanup helper is not a safe reconciler and remains unwired.
2. **Document deletion partial failure:** Qdrant purge happens before SQL document deletion. If SQL deletion fails after vector purge, the document may remain without its vectors. If local-file removal fails after SQL deletion, the file may remain. No durable intent/retry record coordinates these steps.
3. **Late write after document deletion:** a processing request already in flight can complete after the deletion purge. SQL retrieval hydration prevents a deleted document's SQL content from being returned, but late vectors can remain orphaned in Qdrant. This is a cleanup/consistency risk; the SQL gate is not proof that external data is fully purged.
4. **Lease boundary:** attempt tokens/leases protect guarded SQL transitions. They do not fence an external request that already passed its ownership check.

Do not enable automatic cleanup or claim deletion is fully reconciled until deterministic delayed-write tests and an external-write/deletion fencing protocol establish the intended guarantee.

## Next engineering order

- [x] Verify dense-hit identity validation on CI Run #401 for commit `bcc175d02d9202e584aae197fbbd768f1648899a` (687 passed, 2 skipped).
- [ ] Reproduce late-write-after-cleanup and late-write-after-delete races with controllable Qdrant upsert barriers in tests.
- [ ] Specify and validate a write/deletion fencing protocol. A SQL lock held across a synchronous external write is only a candidate; timeout/accepted-but-unacknowledged writes and lock duration must be handled explicitly.
- [ ] Implement durable deletion intent/tombstone and retry checkpoints only after the fence and visibility contract are specified. Cover document detail/list, retrieval, processing claim, and version replacement.
- [ ] Add a durable abandoned-generation claim/reconciler, with idempotent SQL/Qdrant cleanup and explicit terminal/tombstone policy; prove it cannot race late writes.
- [ ] Audit legacy processor callsites, document-wide deletion, storage cleanup, and migration downgrade/upgrade paths. Restrict unsafe legacy operations where feasible without breaking benchmark compatibility.
- [ ] Add focused concurrency/failure tests and run the full CI suite on the exact final commit. Review code, migrations, and docs before declaring the PR complete.

## Engineering changes in this run

- `16391b948ec353e8497d4eab4f79bf6b9967f414` — atomically claim legacy processing and reject generation-managed documents.
- `a4289fa9d4e2991811004146c6474c77f33130fd` — regression test for abandoned-generation documents entering the legacy processor.
- `4d333b10c285fa71d070ee80e3e6e7807390be3e` — lifecycle checklist/status update.
- `25a6c7a58c6086a4014f6c3d32a3413a19e8970a` — corrected stale CI history (this file is being reviewed again because the first update accidentally inserted literal newline escapes).

## CI verification history

- Run [#399](https://github.com/Sujeet-Kona/NEXORA/actions/runs/46016882587) passed for retrieval-integrity commit `e967f83d547808732d28417b4f8c044aeee18c06`: 685 passed, 2 skipped, 5 warnings; PostgreSQL 17 migrations, pip-audit, and byte-compilation succeeded.
- Run [#401](https://github.com/Sujeet-Kona/NEXORA/actions/runs/46017324303) passed for dense retrieval identity/scope regression commit `bcc175d02d9202e584aae197fbbd768f1648899a`: 687 passed, 2 skipped, 5 warnings; PostgreSQL 17 migrations, pip-audit, and byte-compilation succeeded.
- Run [#403](https://github.com/Sujeet-Kona/NEXORA/actions/runs/46152993501) was in progress for legacy-processor atomic-claim code/test commit `a4289fa9d4e2991811004146c6474c77f33130fd`.
- Run [#404](https://github.com/Sujeet-Kona/NEXORA/actions/runs/46153096586) was in progress for status-document commit `4d333b10c285fa71d070ee80e3e6e7807390be3e`.
- Run [#405](https://github.com/Sujeet-Kona/NEXORA/actions/runs/46153203472) was in progress for the latest CI-history correction commit `25a6c7a58c6086a4014f6c3d32a3413a19e8970a`.
- Run [#406](https://github.com/Sujeet-Kona/NEXORA/actions/runs/46153268586) was in progress for the newline/CI-history correction commit `c775c99dc916b7a8118d4a0484902e6c2c7f8dcd`.
- Run [#397](https://github.com/Sujeet-Kona/NEXORA/actions/runs/45831907585) passed for commit `d4fe18d4e18c469c6fc8cd4b077285602c9913c2`: 685 passed, 2 skipped, 5 warnings.

## CI baseline (before this documentation commit)

GitHub Actions run [#392](https://github.com/Sujeet-Kona/NEXORA/actions/runs/45240579052) completed successfully for commit `14fde31300b8f8b1854e00dc3be4fa1700cf8271` on **2026-11-23**:
- Test job: **685 passed, 2 skipped**, 5 warnings (119.45 seconds).
- PostgreSQL 17 service initialized and migrations applied in CI.
- `pip-audit -r requirements.txt`: **No known vulnerabilities found**.
- Byte-compilation step completed successfully.

This is an exact-SHA CI result, not a local test run and not proof of lifecycle concurrency safety. Newer exact-SHA results are listed above; the latest commit's CI must still be terminal before the checklist can close. NEXORA is not being represented as production-ready.
