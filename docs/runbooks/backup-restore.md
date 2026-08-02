# Backup And Restore

PostgreSQL is authoritative. Redis streams, rate-limit counters, and provider
concurrency leases are reconstructible coordination state and are not restored
as business truth.

SPEC-019 semantic-index jobs are also PostgreSQL data. Qdrant vectors are
privacy-sensitive derived data, not anonymous data and not backup authority.
After a PostgreSQL restore, an empty Qdrant instance can be rebuilt by scheduling
an explicit-memory backfill. Reconciliation must remove points for canonical
deleted/inactive memories; deleted content must never return after rebuild.

In an isolated environment, apply migration head, seed synthetic data, run
`pg_dump`, restore into an empty database, then verify migration head, row and
relationship counts, idempotency keys, redaction tombstones, completed outbound
actions, recovery disposition, pending schedule, and summary-content redaction.
Summary text is derived content and must never be included in operator reports.
Start synthetic workers
after restore. Never use production payloads in this rehearsal; delete temporary
dumps or keep them only in ignored local storage.

Run `./scripts/validate-backup-restore.sh` for the local synthetic rehearsal.
