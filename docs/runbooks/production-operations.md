# Production Runtime Operations

This runbook covers the target-neutral lifecycle implemented by SPEC-020. It
does not select a cloud provider or replace the target-specific release
procedure that must be approved before production use.

## Preflight

1. Confirm the approved release image, environment, migration compatibility,
   maintenance window, and rollback owner.
2. Verify required secret references exist without printing values. Confirm
   staging and production namespaces are distinct.
3. Run the canonical validators and the deployment validator:

   `./scripts/validate.sh`

   `./scripts/validate-deployment.sh`

4. Take or verify the PostgreSQL backup and inspect dead letters, quarantines,
   stale leases, and pending work before changing external traffic.
5. Confirm Telegram uses exactly one of webhook or polling mode.
6. Verify bot identity against the approved connection record with the explicit
   SPEC-022 operation; see [`live-acceptance.md`](live-acceptance.md).

## Startup and rollout

1. Start or verify PostgreSQL, Redis, and optional derived services.
2. Run the single-owner migration job and verify the expected Alembic head.
3. Start API replicas and verify `/live`, `/health`, `/ready`, and `/docs`.
4. Start dispatcher and enabled workers. Confirm each role reports healthy
   lifecycle state and no unexpected backlog growth.
5. Register or switch the Telegram webhook only after durable ingress is ready,
   using the explicit SPEC-022 lifecycle operation that verifies the resulting
   Telegram state. Never run polling for the same connection while the webhook
   is active.
6. Run the dedicated staging smoke interaction before accepting traffic.

API startup does not run migrations or start hidden worker loops. Optional
summary, semantic-index, Qdrant, Ollama, and provider capabilities may be
stopped when their documented fallback is safe.

## Graceful shutdown

Send termination to one role at a time where possible. The role must stop
claiming work, finish only work inside the drain budget, release or safely
expire leases, acknowledge only committed work, and close clients. Inspect
pending/reclaimed work after restart. A Telegram request that was already in
flight remains subject to `delivery_unknown`; do not automatically resend it.

## Secret rotation and revocation

Provision the replacement in the approved secret manager, validate it in
staging, restart the affected role through the deployment controller, and
verify the new credential. Revoke the old value only after the replacement is
known good. For suspected compromise, revoke first, fail closed for affected
external I/O, record a content-free incident reference, then replace and
revalidate. Never put the value in shell history, logs, tickets, images, or
health responses.

## Failure and recovery

- **PostgreSQL unavailable:** keep API readiness failed; restore canonical
  service before resuming workers.
- **Redis unavailable:** fail closed for configured external I/O; allow only
  documented database-only mutations; resume after coordination recovers.
- **Qdrant/Ollama unavailable:** keep API ready when semantic fallback is safe;
  rebuild or reconcile derived state from PostgreSQL later.
- **Worker stopped:** allow leases/consumer groups to reclaim work; inspect
  recovery state before replaying anything.
- **Migration failure:** stop rollout, preserve logs without product content,
  restore the approved compatible image if safe, and use a forward corrective
  migration rather than routine production downgrade.
- **Ambiguous Telegram send:** quarantine and use the explicit possible-
  duplicate operator workflow; never use generic replay.

## Rollback and restore

Prefer configuration rollback, compatible image rollback, or disabling the
affected optional capability. Restore PostgreSQL only through the backup/restore
procedure. After restore, reconstruct Redis coordination and rebuild/reconcile
Qdrant from canonical active memories. Verify schema head, redaction,
idempotency, recovery dispositions, and privacy invariants before resuming
workers or Telegram ingress.

## Evidence and cleanup

Record release/configuration identifiers, lifecycle outcomes, dependency
failures, and operator identity without raw messages, prompts, memory text,
vectors, credentials, or provider bodies. Live acceptance runs produce the
content-safe SPEC-022 evidence bundle via
`uv run python -m app.runtime.acceptance_evidence collect --confirm-live-telegram`.
For local validation, run `docker compose down` for the project and verify
`docker compose ps` is empty.
