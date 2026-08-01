# Backup And Restore

PostgreSQL is authoritative. Redis streams, rate-limit counters, and provider
concurrency leases are reconstructible coordination state and are not restored
as business truth.

In an isolated environment, apply migration head, seed synthetic data, run
`pg_dump`, restore into an empty database, then verify migration head, row and
relationship counts, idempotency keys, redaction tombstones, completed outbound
actions, recovery disposition, and pending schedule. Start synthetic workers
after restore. Never use production payloads in this rehearsal; delete temporary
dumps or keep them only in ignored local storage.

Run `./scripts/validate-backup-restore.sh` for the local synthetic rehearsal.
