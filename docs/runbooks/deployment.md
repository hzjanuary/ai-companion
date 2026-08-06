# Deployment

SPEC-020 adds the target-neutral deployment lifecycle and staging-shaped
Compose artifact. Use `docs/runbooks/production-operations.md` for startup,
drain, secret rotation, failure recovery, rollback, and evidence requirements.
`compose.staging.yaml` requires externally supplied values and contains no
production secret defaults; it is not a production orchestrator contract.

Before deployment run the canonical validators, take a PostgreSQL backup, check
schema compatibility, and verify required secret *presence* without printing
values. Preflight that Telegram uses exactly one of polling or webhook mode.

Start PostgreSQL, Redis, API, dispatcher, conversation worker, command worker,
planning worker, outbound worker, then retention worker. Configure rate limits
and provider concurrency independently. Before restarting after an incident,
inspect dead letters and quarantines. Roll back application code when possible;
database downgrade is an exceptional, explicitly scoped recovery action.

The optional conversation-summary worker starts only when both summary flags are
enabled. It can be stopped independently without interrupting raw-history
planning. To roll back summary behavior, disable both flags; do not delete the
stored summaries because retention and privacy cleanup still apply.

The optional semantic-memory index worker starts separately. PostgreSQL remains
authoritative; stop semantic query use by disabling both semantic flags, then
continue deletion/reconciliation work from canonical PostgreSQL state as needed.
