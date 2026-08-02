# January Architecture

January is a modular monolith. It will grow into independently scalable API,
worker, and sender runtime processes without splitting product behavior into
services prematurely.

## Dependency Direction

```text
domain
  <- application
      <- infrastructure
          <- interface
              <- runtime surfaces
```

Dependencies point toward the left. The domain is framework-independent;
application code coordinates use cases; infrastructure implements external
ports; interfaces translate transport input and output; runtime surfaces wire
the application together.

SPEC-002 adds concrete domain records, application persistence ports, and
PostgreSQL infrastructure. It still avoids speculative modules.

## Boundary Rules

- Framework and provider clients stay outside the domain layer.
- Telegram, Zalo, LLM, database, and queue SDKs stay outside inner layers.
- Unknown external input is parsed at interfaces before it enters inner layers.
- Future model-generated actions are validated by application policy before
  execution by an adapter.
- Operational logs describe runtime behavior; product audit records are a
  separate future persistence concern.
- Current readiness reports only the running application. It does not claim
  health for future dependencies.

## Current Layout

```text
backend/app/
  core/          settings, logging, request context
  domain/        platform-independent persistence records and enums
  application/   persistence and platform-independent ingress contracts
  infrastructure/database/ async engine, models, repositories, migrations
  infrastructure/telegram/ typed Bot API HTTP adapter and Update DTOs
  infrastructure/queue/ Redis Streams ingress queue
  interface/http/ response models, routes, middleware
  runtime/       dedicated polling and outbox dispatch entry points
  main.py        application factory and API runtime entry point
```

The factory is the composition boundary. New modules are introduced only with
the first behavior that needs them.

SPEC-004 keeps Telegram raw payloads and SDK contracts in infrastructure. The
application ingress envelope is platform independent; PostgreSQL owns durable
deduplication and outbox intent; Redis Streams transports references only.

SPEC-005 consumes those references in a dedicated runtime. Telegram payloads
are normalized before application policy runs; PostgreSQL commits normalized
conversation state and the idempotency ledger before Redis acknowledgement.
Context readers return application values rather than ORM models, raw payloads,
or credentials. No LLM or outgoing-delivery dependency crosses this boundary.

SPEC-006 adds a separate response-planning runtime. Provider HTTP JSON remains
in infrastructure; application values carry only typed generation requests,
results, and safe errors. PostgreSQL leases and immutable response plans make
planning durable without claiming exactly-once generation or executing any
platform action.

SPEC-007 compiles response plans to ordered platform-independent actions in the
planning transaction. Its sender is a separate runtime: PostgreSQL owns action
leases, attempts, and outgoing-message linkage; Telegram rendering and asset
references stay in infrastructure. A send timeout or malformed post-send
response is terminal `delivery_unknown`, deliberately avoiding automatic
duplicate visible messages rather than claiming exactly-once delivery.

SPEC-008 adds only explicit runtime composition for local operators. Demo
allowlisting happens before conversation persistence, bootstrap reconciles safe
identity metadata transactionally, and all five workers remain separate from
the API process.

SPEC-009 adds typed personality values in `application` and immutable profile
and conversation-configuration persistence in `infrastructure/database`.
Operator mutation remains a local runtime CLI; no personality HTTP or Telegram
command surface exists. Planning receives immutable job snapshots and performs
provider I/O only after checking the current conversation safety projection.
Outbound delivery similarly checks current sticker enablement immediately before
Telegram I/O. ORM models and provider/platform clients do not enter the
personality application module.

SPEC-010 parses Telegram command entities only at the infrastructure boundary,
then writes a durable command job before ordinary model eligibility. A dedicated
command runtime performs fresh group authorization through the platform port and
creates the same response-plan/outbound-action handoff used by model work.
Command jobs, response plans, and delivery remain independently scalable
runtime processes; command parsing and grammar do not import provider clients.

SPEC-011 keeps explicit-memory contracts in `application`, while PostgreSQL
owns scoped memory rows, content-free events, physical redaction, and retention
batching. Context includes only active records belonging to the exact
Assistant, platform connection, and conversation; memory enters provider input
only as JSON-delimited untrusted data. Privacy and memory mutations advance a
durable conversation revision that planning rechecks immediately before
provider I/O. The retention runtime owns no Telegram, Redis, or provider client
and is separate from API startup.

SPEC-012 keeps hard safety policy and rate-limit contracts in the inner layers.
Redis is an infrastructure implementation of atomic multi-scope coordination;
enabled coordination is required for provider and Telegram I/O, while command
and privacy database mutations remain independent. Content-free PostgreSQL
decision records and the inspector expose policy state without unsafe content.

SPEC-013 verifies only that Zalo OA, OA messaging, GMF, and webhook are distinct
official product surfaces. Zalo runtime work remains deferred pending dedicated
test OA/app verification of auth, webhook, and GMF semantics. The core remains
platform-neutral; Telegram-specific assumptions, candidate schema risks, and
reusable boundaries are documented in `docs/platforms/zalo/` without adding a
platform enum, adapter, migration, or runtime dependency.

SPEC-014's repository preparation is complete, but its live verification is
`DEFERRED / BLOCKED_ON_EXTERNAL_PREREQUISITE` until an operator-owned dedicated
nonproduction OA/application exists. This Zalo-only dependency is outside the
Telegram MVP critical path; the next implementation specification is SPEC-015
for accepted Telegram/product work only.

SPEC-015 adds a platform-neutral application telemetry port. Each API or worker
runtime owns a process-local infrastructure registry; an external collector may
aggregate replicas. Prometheus-text export is an optional local runtime surface
and never enters domain/application policy or readiness dependencies.

SPEC-016 preserves the same direction: recovery vocabulary and concurrency
ports are inner contracts, while PostgreSQL recovery history, transaction
advisory ordering locks, and Redis TTL provider leases remain infrastructure.
PostgreSQL serializes durable processing of one conversation/topic only within
its business transaction; no lock spans provider or Telegram I/O. Recovery
history contains opaque internal work IDs and closed classes only. A generic
dead letter can re-enter normal scheduling once; a quarantine, including an
ambiguous Telegram delivery, is intentionally not generically replayable.

SPEC-017 keeps ambient participation policy in inner typed contracts. PostgreSQL
retains immutable frequency revisions, trigger/origin, and confirmed delivery
timestamps; Redis remains rate/concurrency coordination only. Sampling uses
opaque internal IDs and no content.

SPEC-018 keeps conversation summaries outside the domain as short-lived derived
context. PostgreSQL stores summary jobs and content under the same conversation/
thread boundary, while provider I/O stays in an optional runtime worker. Summary
source windows use only retained raw messages; summaries never become input to
later summaries and expire at the earliest represented raw-content deadline.
