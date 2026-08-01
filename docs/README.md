# Documentation Map

Start with the smallest current map. Retrieve compatibility, historical, or
upstream-maintenance material only when the task explicitly needs it.

## Installed Core

- `WORKFLOW.md`: canonical request, planning, judgment, validation, and
  completion behavior.
- `product/`: consumer-owned product behavior derived from accepted intent.
- `plans/`: one evolving Git-native plan for work that needs durable memory.
- `decisions/`: lasting product and architecture choices.
- `templates/decision.md`: lasting-decision template.
- `templates/exec-plan.md`: durable execution-plan template.
- `.agents/skills/onboard-repository/`: explicit, read-only-first brownfield
  repository mapping and improvement proposals.
- `.agents/skills/audit-onboarding-proposal/`: explicit independent proposal
  and patch verification.

These files are generic Harness structure. They do not select an application
stack, replace a consumer README or architecture, fabricate validation
commands, or require the optional SQLite control-plane lifecycle. The installed
`harness` binary only maintains this core structure. The skills do not run
automatically; invoke `$onboard-repository` only when repository onboarding is
the requested outcome.

## Consumer-Owned Truth

The consumer repository's own README, architecture, code, tests, CI, runtime
signals, and application behavior remain authoritative. Harness adds navigation
and working-memory structure around that truth; it does not install upstream
`repository-harness` product documents over it.

## January Application

- `product/SPEC.md`: canonical product contract.
- `ARCHITECTURE.md`: January's module boundaries and runtime shape.
- `HARNESS.md`: installed Harness status and its repository-centered boundary.
- `runbooks/local-development.md`: backend setup, validation, and local runtime.
- `runbooks/safety-rate-limiting.md`: SPEC-012 deterministic safety and Redis
  limiter operation and validation.
- `runbooks/observability.md`: SPEC-015 metrics, safe logging, local exporter,
  pricing estimate, and operator inspection boundary.
- `runbooks/recovery.md`: SPEC-016 dead-letter/quarantine and one-item replay.
- `runbooks/backup-restore.md`: PostgreSQL authoritative backup rehearsal.
- `runbooks/deployment.md`: local deployment/restart safety order.
- `runbooks/ambient-participation.md`: SPEC-017 opt-in ambient policy and rollback.
- `platforms/zalo/`: SPEC-013 official-source register, capability matrix,
  parity analysis, and verification-gate decision; no Zalo runtime support.
- `platforms/zalo/operator-verification-plan.md`: SPEC-014 redacted,
  operator-controlled live-verification gate. It is deferred from the Telegram
  MVP critical path and blocked only on its external OA/application prerequisite.
- `plans/active/telegram-social-ai-mvp.md`: durable MVP execution plan.
- `decisions/0001-backend-bootstrap-boundaries.md`: accepted bootstrap architecture decision.
- `product/specs/SPEC-002-database-and-persistence.md`: accepted persistence
  outcome, model boundaries, and validation requirements.
- `decisions/0002-postgresql-persistence-foundation.md`: accepted PostgreSQL
  persistence strategy.
- `product/specs/SPEC-004-telegram-ingress-queue-idempotency.md`: accepted
  Telegram delivery, durable inbox/outbox, and Redis Streams behavior.
- `decisions/0004-telegram-durable-ingress.md`: accepted ingress delivery and
  idempotency strategy.
- `product/specs/SPEC-007-outbound-actions-delivery-idempotency.md`: durable
  response-plan delivery, ambiguity policy, and recovery boundary.
- `decisions/0007-outbound-delivery-ambiguity.md`: lasting no-exactly-once
  Telegram delivery decision.
- `product/specs/SPEC-010-telegram-administration-commands-and-user-preferences.md`:
  deterministic Telegram command and preference behavior.
- `decisions/0010-telegram-command-jobs-and-fresh-authorization.md`: command
  parsing, durable handoff, and fresh authorization decision.

## Source-Repository Indexes

The following material is deliberately outside the default installation:

- [Application-legibility plan](https://github.com/hoangnb24/repository-harness/blob/main/docs/plans/active/application-legibility.md): current consumer-first evidence matrix and next gate.
- [Control-plane freeze decision](https://github.com/hoangnb24/repository-harness/blob/main/docs/decisions/0022-control-plane-freeze-and-compatibility-runway.md): current compatibility boundary for SQLite and protocol v1.
- [Optional-consumer ownership decision](https://github.com/hoangnb24/repository-harness/blob/main/docs/decisions/0023-optional-consumer-ownership.md): current ownership split between Harness, Symphony, and consumer applications.
- [Test suite map](https://github.com/hoangnb24/repository-harness/blob/main/tests/README.md): behavior protected by each current, compatibility, and historical test group.
- [CLI compatibility index](https://github.com/hoangnb24/repository-harness/blob/main/docs/compatibility/README.md): SQLite lifecycle, orchestration protocol, bootstrap, schemas, and CLI maintenance.
- [Historical index](https://github.com/hoangnb24/repository-harness/blob/main/docs/provenance/README.md): superseded decisions, story-era evidence, reviews, and migration provenance.
- [Upstream repository](https://github.com/hoangnb24/repository-harness): Rust implementation, installer, release, and maintenance truth.

Selecting the optional CLI profile installs the compatibility material required
to operate that surface. Historical and upstream-only material remains in the
source repository and Git history.
