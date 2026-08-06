# SPEC-019 Engineering Handoff

This document is a continuation brief for a coding agent that has not worked
on January before. It describes the repository as observed at handoff time;
the repository, executable code, tests, migrations, and current Git state are
authoritative if this document disagrees with older planning prose.

## 1. Repository State

- **HEAD:** `fab18171d2b5b34728018b00cefb0add1c7d274c`
- **Branch:** `main`
- **Status:** clean at inspection time before this handoff; no staged, unstaged,
  or untracked changes were present. After creating this requested document,
  the only worktree change is the new untracked handoff file itself.
- **Latest completed SPEC:** SPEC-019, Explicit Memory Semantic Retrieval and
  Qdrant Derived Index. The HEAD commit is `feat: complete SPEC-019 semantic
  memory retrieval`.
- **Deferred SPEC:** SPEC-014, Zalo Operator Verification Gate. Its state is
  `DEFERRED / BLOCKED_ON_EXTERNAL_PREREQUISITE` because there is no
  operator-owned dedicated nonproduction Zalo OA/application environment.
  This does not block the Telegram MVP path.
- **Current architecture version:** the SPEC-019 architecture and schema
  state: modular monolith, PostgreSQL/Alembic revision
  `0013_semantic_memory_index`, Redis Streams coordination, and an optional
  Qdrant-derived semantic-memory index. Qdrant is never canonical storage.
- **Product state:** SPEC-001 through SPEC-013 and SPEC-015 through SPEC-019
  are implemented/completed in the current repository. The active execution
  plan still contains historical progress prose from earlier SPECs; use Git,
  current code, and current validator results as the final authority.

Important entry points:

- Product contract: `docs/product/SPEC.md`
- SPEC index: `docs/product/README.md`
- Architecture: `docs/ARCHITECTURE.md`
- Active execution history: `docs/plans/active/telegram-social-ai-mvp.md`
- Runtime/operator runbooks: `docs/runbooks/`
- Python application: `backend/app/`
- Migrations: `alembic/versions/`
- Validators: `scripts/`

## 2. Product Progress

### SPEC-001 — Repository and Backend Bootstrap

**Completed.** Established the Python 3.12 FastAPI backend, configuration,
logging, request IDs, safe HTTP error handling, Docker image, Compose baseline,
validation entrypoint, and initial repository workflow. It established the
composition boundary without speculative future modules.

### SPEC-002 — Database and Persistence Foundation

**Completed.** Added PostgreSQL 16, SQLAlchemy async sessions, asyncpg,
Alembic, UUID/UTC/JSONB conventions, and the core Assistant,
PlatformConnection, Conversation, Participant, and Message records. Database
readiness is distinct from process liveness.

### SPEC-003 — Telegram Platform Adapter

**Completed.** Added a typed, lifecycle-managed infrastructure adapter for
`getMe`, text/reply sends, stickers, and chat-member lookup. Telegram DTOs,
tokens, HTTP details, and provider errors remain outside inner layers. Update
delivery was intentionally deferred to SPEC-004.

### SPEC-004 — Telegram Ingress, Queue, and Idempotency

**Completed.** Added secure webhook and controlled polling modes, typed update
parsing, PostgreSQL durable inbox/outbox/cursor state, Redis Streams reference
events, at-least-once delivery, and update-ID deduplication. Webhook and
polling are mutually exclusive and disabled by default.

### SPEC-005 — Conversation Domain and Context

**Completed.** Added platform-neutral normalization into conversations,
participants, messages, membership state, deterministic eligibility, bounded
same-conversation/topic context, and a processing ledger. Conversation work
commits before queue acknowledgement and does not call a provider or sender.

### SPEC-006 — LLM Provider and Response Planning

**Completed.** Added provider-neutral structured response planning with typed
adapters for OpenAI, Gemini, Groq, OpenRouter, and Ollama; leased planning
jobs, durable attempts/plans, bounded retries/correction/fallback, strict
local validation, and explicit silence. Planning never sends platform actions.

### SPEC-007 — Outbound Actions, Delivery, and Idempotency

**Completed.** Compiles accepted plans into ordered text/sticker actions with
idempotency keys. A separate sender leases actions and persists confirmed
Telegram results. Timeouts, transport failures, and malformed post-send
responses become terminal `delivery_unknown` and are not automatically
retried because a duplicate visible send is possible.

### SPEC-008 — Operator Bootstrap and End-to-End Demo

**Completed.** Added a guarded, polling-only local demo for a dedicated test
bot, transactional identity bootstrap/reconciliation, allowlist suppression,
operator discovery/inspection, and separate worker processes. Synthetic proof
uses fake adapters; live Telegram/provider use requires explicit operator
confirmation and is never normal CI validation.

### SPEC-009 — Personality Profiles and Group Configuration

**Completed.** Added immutable typed personality profile versions and
conversation configuration revisions, deterministic defaults, immutable job
snapshots, pause/sticker rechecks, and a safe local operator CLI. Custom prompt
text, private-memory disclosure, unsafe teasing, and mutable-in-place profile
changes are not allowed.

### SPEC-010 — Telegram Administration Commands and User Preferences

**Completed.** Added strict Telegram UTF-16 command parsing, durable command
jobs, fresh group authorization, preference/configuration mutations, memory
command routing, and a dedicated command worker. Command work uses the same
response-plan/outbound pipeline and remains separate from ordinary model
eligibility.

### SPEC-011 — Explicit Memory, Privacy, and Retention

**Completed.** Added scoped explicit memory, privacy revisions, content-free
memory events, physical redaction, exact-scope context selection, deterministic
forget/reset commands, and a retention worker. Private data is not allowed to
cross conversation boundaries; terminal content is retained only until its
policy deadline.

### SPEC-012 — Safety Policy and Distributed Rate Limiting

**Completed.** Added hard safety policy, content-free safety decisions, Redis
atomic fixed-window coordination, generation and delivery scopes, fail-closed
coordination behavior, provider/Telegram rechecks immediately before external
I/O, and bounded structural response metadata.

### SPEC-013 — Zalo Feasibility Spike and Capability Matrix

**Completed.** Recorded official-source-only Zalo OA/GMF feasibility evidence.
The result is that Zalo OA, messaging, webhooks, and GMF are distinct surfaces;
private friend-group parity is not established. No Zalo runtime, enum,
migration, credential, or adapter was introduced.

### SPEC-014 — Zalo Operator Verification Gate

**Deferred.** Added redacted verification artifacts, source/result schemas,
credential guards, and static validators. Authenticated OA, app, webhook,
direct-message, GMF, and commercial checks remain `NOT_RUN` until a dedicated
nonproduction OA/application is supplied and each external action is approved.

### SPEC-015 — Telegram MVP Observability and Operational Telemetry

**Completed.** Added a platform-neutral metrics port, process-local registries,
optional loopback Prometheus-text export, request/correlation context, typed
operational events, bounded metric definitions, and HTTP/ingress/conversation/
planning/outbound instrumentation. Metrics are not readiness dependencies.

### SPEC-016 — Telegram Operational Reliability, Recovery, and Scale

**Completed.** Added recovery vocabulary and durable content-free recovery
items/events, dead-letter versus quarantine behavior, bounded replay, stale
lease handling, PostgreSQL advisory ordering locks, Redis provider concurrency
leases, backup/restore rehearsal, and synthetic multi-worker burst proofs.
Ambiguous external delivery is quarantined and is not generically replayable.

### SPEC-017 — Telegram Ambient Selective Participation

**Completed.** Added opt-in ambient participation with immutable frequency
revisions, addressed-versus-ambient origin/trigger state, opaque sampling,
Redis coordination, and confirmed-delivery timestamps. Ambient work is still
subject to safety, rate, concurrency, configuration, and delivery checks.

### SPEC-018 — Telegram Conversation Summaries and Bounded Context Compression

**Completed.** Added optional derived conversation summaries and summary jobs,
bounded retained-source windows, provider-gated summary generation, summary
expiry at the earliest represented raw-content deadline, privacy invalidation,
and non-overlapping summary-plus-raw context. Summaries never summarize other
summaries and are not explicit memory.

### SPEC-019 — Explicit Memory Semantic Retrieval and Qdrant Derived Index

**Completed.** Added versioned embedding/index ports, Ollama and direct Qdrant
REST infrastructure adapters, default-off settings, durable content-free
semantic index jobs, a separate index worker, PostgreSQL-routed physical
collections, rebuild/backfill/reconcile operations, exact scope filtering,
mandatory PostgreSQL revalidation, bounded semantic telemetry, and deterministic
fallback to existing explicit-memory selection. The canonical text and active/
deleted state remain in PostgreSQL; Qdrant stores vectors plus approved opaque
metadata only.

## 3. Current Architecture

January is a modular monolith designed so API, workers, and sender processes
can scale independently without prematurely splitting product behavior into
services.

### Backend and dependency direction

The dependency direction is:

```text
domain <- application <- infrastructure <- interface <- runtime surfaces
```

`domain` contains framework-independent records and policy vocabulary.
`application` contains use cases and ports. `infrastructure` implements
PostgreSQL, Redis, Telegram, model, embedding, Qdrant, telemetry, and rate/
concurrency adapters. `interface` translates HTTP/transport input. `runtime`
modules compose workers and operator commands. Provider/platform SDKs and raw
payloads must not enter inner layers.

### Workers and queues

Redis Streams carry references, not raw Telegram payloads. PostgreSQL is the
durable authority for inbox deduplication, processing ledgers, leases, plans,
actions, retries, and recovery state. A queue acknowledgement follows the
corresponding durable transaction.

### Database

PostgreSQL 16 is the source of truth for identity, conversations, participants,
messages, configuration, memory, summaries, planning, delivery, safety, rate
events, and recovery. Alembic migration head is `0013_semantic_memory_index`.

### Redis

Redis Streams transport ingress references. Redis also provides atomic
distributed rate-limit windows and TTL-based provider concurrency leases.
When required coordination is unavailable, provider and Telegram I/O fail
closed; database-only command/privacy operations retain their explicit
exemption.

### Qdrant

Qdrant is optional and derived. It contains vectors and content-free opaque
payload fields: `memory_id`, `assistant_id`, `platform_connection_id`,
`conversation_id`, `scope`, and `embedding_version`. A PostgreSQL routing row
selects the active physical collection for an embedding version only after a
rebuild verifies its opaque IDs. Old collections remain derived recovery
artifacts. Missing Qdrant, embedding errors, stale points, and disabled
semantic memory fall back to deterministic PostgreSQL memory selection.

### Telegram

Telegram is an adapter only. Webhook and polling ingress are mutually
exclusive. Sending is performed by the outbound worker after plan validation,
current safety/configuration checks, rate/concurrency acquisition, and
infrastructure rendering. No Telegram credential is persisted in domain data.

### Memory and context

Explicit memory is user/command-created canonical data scoped by Assistant,
platform connection, conversation, visibility, and active state. Deletion
physically clears content/hash and records content-free audit events. Semantic
retrieval queries only incoming-message text, filters exact scope/version in
Qdrant, and re-fetches/revalidates PostgreSQL rows before text enters provider
context. Existing deterministic explicit-memory fallback remains available.

Conversation summaries are separate derived context. They use retained raw
messages from the same conversation/thread, expire with their earliest source,
are invalidated by privacy operations, and are excluded from semantic memory.

### Ambient participation

Ambient sampling is opt-in and frequency-revisioned. It uses opaque internal
IDs and no content in sampling/coordination. The selected work enters normal
planning and delivery policy with an `ambient` origin and must still pass all
current safety, rate, concurrency, pause, and stale-configuration checks.

### Recovery, observability, safety, and concurrency

Retryable failures use bounded backoff and leased work. One generic replayable
dead letter may re-enter normal scheduling; quarantines, especially ambiguous
Telegram deliveries, require explicit operator handling. PostgreSQL advisory
locks serialize durable same-conversation ordering without spanning provider or
Telegram I/O. Redis leases coordinate provider capacity across workers.

Operational metrics are bounded and content-free. Do not add message text,
memory IDs, query text, vectors, credentials, or provider bodies as metric
labels or log fields. Safety decisions are persisted without unsafe content;
hard boundaries and rate limits fail closed where external I/O is involved.

### Planning and response generation

The conversation worker creates durable planning jobs for deterministic eligible
messages. The planning worker leases a job, rebuilds bounded context, snapshots
configuration/personality, performs safety and rate/concurrency checks, calls a
typed model provider, validates structured output locally, and persists one
platform-neutral response plan. The outbound worker compiles/leases ordered
actions and sends through the Telegram adapter. Silence creates no outbound
action.

### Repository layout

```text
backend/app/core/             settings, logging, request/telemetry context
backend/app/domain/           inner records, safety, recovery, planning types
backend/app/application/      use cases and provider/platform/persistence ports
backend/app/infrastructure/   database, Redis, Telegram, providers, Qdrant,
                              rate/concurrency, telemetry
backend/app/interface/http/   FastAPI routes, models, middleware
backend/app/runtime/          pollers, workers, operators, inspectors
backend/tests/                unit and integration proof
alembic/versions/             ordered schema migrations
docs/product/                 accepted SPECs and product contract
docs/decisions/               lasting architectural decisions
docs/runbooks/                operator and recovery procedures
scripts/                      validation and verification entrypoints
```

## 4. Runtime Components

All durable workers use PostgreSQL leases or transaction boundaries and are
safe for at-least-once orchestration. Workers do not hold database locks while
performing provider or Telegram HTTP.

| Runtime | Purpose, inputs, outputs, failure/idempotency behavior |
|---|---|
| `telegram_poller` | Optional Telegram long-poll ingress. Reads Telegram updates and cursor state; writes durable inbox/outbox/cursor data. Refuses to run when a webhook is configured. Retries retryable adapter failures with bounded backoff; cursor advances only after durability. |
| `ingress_outbox_dispatcher` | Publishes durable ingress outbox references to Redis Streams. Reads pending outbox rows; outputs Stream entries and published state. A crash can duplicate publication, so consumers deduplicate by stable incoming update ID. Publication failures remain retryable. |
| `conversation_worker` | Consumes ingress references, loads/parses normalized state, writes participants/messages/membership, processing records, and planning handoff. Acknowledges only after commit. Duplicate updates become safe no-ops; stale Redis entries can be reclaimed. |
| `response_planning_worker` | Leases planning jobs, assembles context/personality/summary/memory, gates external work, calls a configured model adapter, validates/corrects structured output, and writes response plans or recovery state. Provider errors retry within bounds; safety, rate, context, and privacy failures avoid provider I/O. |
| `telegram_command_worker` | Leases durable Telegram command jobs, performs fresh authorization, applies preferences/configuration/memory/privacy commands, and may create normal response-plan/outbound work. Database-only mutations are idempotent and content-free; retryable platform authorization failures are bounded. |
| `outbound_delivery_worker` | Leases ordered outbound actions, rechecks current safety/configuration/ambient state, acquires rate/concurrency coordination, renders Telegram requests, and records delivery attempts/messages. Known bounded rejects may retry; ambiguous external results become terminal quarantine/`delivery_unknown` to avoid duplicate visible sends. |
| `retention_worker` | Deletes/redacts expired terminal content and related derived records according to retention boundaries. Inputs are due retention rows; output is physical redaction and content-free completion. Batch work is repeatable and has no Telegram, Redis, or provider dependency. |
| `conversation_summary_worker` | Optional derived-summary worker. Leases summary jobs, reads only the bounded retained source window, calls a configured provider after gates, and stores a summary with exact source/expiry metadata. No summary-of-summary input; failures release/retry or complete as safely invalidated. |
| `semantic_memory_index_worker` | Optional embedding/Qdrant worker. Leases content-free UPSERT/DELETE jobs, rechecks canonical PostgreSQL memory state before embedding, calls the embedding adapter, and writes/deletes derived Qdrant points. Deletion is safe if a collection is absent; retries use bounded backoff and terminal failures are content-free. |

Operator-only runtime commands include `semantic_memory_operations` for
status/backfill/reconcile/rebuild, `operations` for inspection/recovery state,
`outbound_recovery` for explicitly confirmed possible-duplicate replay,
`operator_bootstrap`, `demo_inspector`, `group_configuration`, and discovery.
They are not long-running workers.

## 5. Database

### Migration chain

Migrations are strictly ordered and must never be renumbered:

1. `0001_initial_persistence`
2. `0002_telegram_ingress`
3. `0003_conversation_domain`
4. `0004_response_planning`
5. `0005_outbound_delivery`
6. `0006_personality_config`
7. `0007_telegram_commands`
8. `0008_memory_privacy_retention`
9. `0009_safety_rate_limiting`
10. `0010_operational_recovery`
11. `0011_ambient_participation`
12. `0012_conversation_summaries`
13. `0013_explicit_memory_semantic_index` (revision string
    `0013_semantic_memory_index`)

Current migration head is `0013_semantic_memory_index`. The constrained
revision string length is an existing compatibility constraint; do not casually
rename it. Validators exercise upgrade, downgrade, and re-upgrade paths.

### Major tables and relationships

- Identity/configuration: `assistants`, `platform_connections`,
  `conversations`, `participants`, `personality_profiles`,
  `personality_profile_versions`, and
  `conversation_configuration_revisions`.
- Conversation ingress/state: `incoming_platform_updates`,
  `ingress_outbox_events`, `polling_cursors`, `messages`, and
  `conversation_processing_records`.
- Planning/commands: `response_planning_jobs`, `model_generation_attempts`,
  `response_plans`, and `telegram_command_jobs`.
- Delivery: `outbound_actions`, `outbound_delivery_attempts`, and
  `outbound_recovery_events`.
- Privacy/memory: `memory_items`, `memory_events`,
  `explicit_memory_semantic_index_jobs`, and
  `explicit_memory_semantic_index_collections`.
- Derived summaries: `conversation_summaries` and
  `conversation_summary_jobs`.
- Policy/operations: `participant_preference_events`,
  `safety_policy_decisions`, `rate_limit_events`,
  `operational_recovery_items`, and `operational_recovery_events`.

The primary ownership path is Assistant -> PlatformConnection -> Conversation
-> Participant/Message and all scoped derived work. Planning jobs point to
conversation processing/message state; response plans point to planning jobs;
ordered outbound actions point to response plans and conversation state.

### Privacy and retention invariants

Memory and context queries require exact Assistant, platform connection, and
conversation scope, plus active/current visibility checks. `/forget`,
`/memory reset_group`, and `/forget_me confirm` advance the conversation privacy
revision. Canonical deleted memory content and normalized hashes are physically
cleared; audit/event rows contain codes, IDs, counts, and timestamps, not raw
content. Raw message content and summaries are retained only within their
documented deadlines. A summary cannot outlive its earliest represented raw
source. Qdrant is never used to bypass PostgreSQL privacy or retention checks.

### Semantic index lifecycle

`explicit_memory_semantic_index_jobs` stores content-free operation metadata,
embedding version, target collection, lease/retry state, and error category.
`explicit_memory_semantic_index_collections` stores the PostgreSQL routing
record for physical collection name/version/activation state. A rebuild writes
to a fresh compatible collection, indexes canonical active rows, verifies exact
opaque IDs against PostgreSQL, then activates the route. Backfill only targets
canonical IDs absent from the active index; reconcile removes stale points.

## 6. Validation Matrix

The validators are executable proof boundaries, not merely status labels. Most
integration validators start only project-owned PostgreSQL/Redis/Qdrant
services, use fake adapters, and stop those services with traps. No normal
validator uses a real Telegram token or model request.

| Validator | What it proves |
|---|---|
| `validate.sh` | Full selected no-network pytest suite, Ruff lint, format check, strict mypy, Harness status/doctor, and `git diff --check`. |
| `validate-db.sh` | PostgreSQL startup/readiness, Alembic upgrade to head, database integration tests, downgrade to base, and re-upgrade to head. |
| `validate-ingress.sh` | PostgreSQL/Redis ingress integration: webhook idempotency, durable outbox publication, Stream acknowledgement/reclaim, and polling cursor behavior. |
| `validate-conversation.sh` | Durable normalization/processing, commit-before-ack, duplicate safety, and conversation-worker reclaim behavior. |
| `validate-planning.sh` | Planning leases, context/policy handoff, provider-neutral fake generation, validation, retry/fallback, and no external provider calls. |
| `validate-delivery.sh` | Ordered action lifecycle, Telegram rendering with fake adapters, delivery idempotency, rejection/unknown outcomes, and integration pipeline. |
| `validate-demo.sh` | Guarded local-demo settings and synthetic bootstrap-to-delivery flow, allowlist suppression, replay safety, and fake-adapter operation. |
| `validate-personality.sh` | Profile/config schema, immutable revisions/default reconciliation, migration lifecycle, snapshots, isolation, pause behavior, and stale sticker suppression. |
| `validate-commands.sh` | Telegram command grammar/entity rules, durable command jobs, fresh authorization, preference/configuration/memory command effects, replay, and integration delivery. |
| `validate-memory.sh` | Explicit-memory unit/context tests, PostgreSQL/Redis privacy and retention behavior, content-free inspection, deletion/idempotence, and downgrade from head to `0007` then re-upgrade. |
| `validate-safety.sh` | Safety policy and Redis rate-limit scopes, atomic final-token behavior, expiry, content-free coordination, fail-closed outage behavior, and `0008 -> 0009 -> 0008 -> head`. |
| `validate-observability.sh` | Bounded metric definitions and instrumentation, HTTP/planning tests, required metric families, and prohibition of a SPEC-015 migration. |
| `validate-reliability.sh` | Focused reliability tests plus database, ingress, conversation, planning, delivery, commands, memory, safety, Redis concurrency, and backup/restore validators. |
| `validate-scalability.sh` | Synthetic multi-worker PostgreSQL/Redis ingress/processing/delivery concurrency proof. It is not a production SLO benchmark. |
| `validate-ambient.sh` | Ambient policy/eligibility tests and the underlying database/ingress proof for frequency revisions, triggers, origins, and delivery coordination. |
| `validate-summaries.sh` | Summary/context/observability tests, database lifecycle, Ruff, and mypy; proves derived summary behavior without provider or Telegram I/O. |
| `validate-semantic-memory.sh` | PostgreSQL/Redis/Qdrant health, semantic-memory unit and integration tests, Qdrant scope/payload/revalidation/rebuild behavior, and `0012 -> 0013 -> 0012 -> 0013`. |
| `validate-backup-restore.sh` | Synthetic PostgreSQL dump/restore preserving migration revision, redaction, delivery idempotency, safety/rate records, and recovery dispositions without leaking content. |
| `validate-zalo-feasibility.sh` | Official-source register, capability matrix, evidence enums, baseline checkpoint, credential guard, and absence of runtime/migration scope changes. |
| `validate-zalo-verification.sh` | Redacted operator-verification artifact shape, ignored local-secret boundaries, `NOT_RUN`/approval state, and no unauthorized Zalo mutation or credential exposure. |
| `verify-telegram.sh` | Explicit operator-only Telegram `getMe` verification; rejects missing/unsafe configuration and is not normal CI proof. |
| `verify-telegram-delivery.sh` | Explicitly opt-in Telegram delivery verification with dedicated test configuration; never assume a real send occurred from synthetic tests. |
| `verify-model-provider.sh` | Explicit provider verification path; requires configured opt-in and uses the provider contract, not ordinary validation. |

When a validator invokes nested validators, preserve its cleanup and port
conventions. Docker tests can collide with existing services; use isolated
host ports and inspect `docker compose ps` before claiming cleanup.

## 7. Docker Validation Requirements

Before approving any future SPEC or claiming runtime validation, perform the
following sequence with only project-owned resources and explicit isolated
ports when needed:

1. Build the image:

   ```bash
   docker build --tag january-backend:spec-NNN .
   ```

2. Validate Compose expansion:

   ```bash
   docker compose config
   ```

3. Start the required project services and wait for PostgreSQL, Redis, and
   Qdrant (when semantic-memory validation is in scope) health/readiness.
   Apply migrations in the backend/container environment:

   ```bash
   docker compose up --detach database redis qdrant backend
   docker compose exec -T backend uv run alembic upgrade head
   ```

4. Verify the HTTP operational surface:

   ```text
   GET /       -> 200
   GET /health -> 200
   GET /live   -> 200
   GET /ready  -> 200
   GET /docs   -> 200
   ```

   The exact host port may be overridden with `JANUARY_HOST_PORT`. Telegram,
   LLM, outbound delivery, and semantic memory are normally disabled for this
   endpoint smoke test unless the SPEC explicitly requires a separate fake or
   isolated runtime proof.

5. Prove readiness failure, not just success. Stop one required dependency
   while the backend remains running (normally PostgreSQL, and Redis when
   enabled), then verify `/ready` returns HTTP 503 with a safe request-ID-bearing
   response. Restart the dependency and verify readiness recovers to 200. A
   Qdrant outage alone must not make readiness fail when semantic retrieval is
   optional; semantic query failure must use PostgreSQL fallback.

6. For migration work, exercise the relevant downgrade and re-upgrade path,
   not only `upgrade head`. For SPEC-019 the mandatory focused path is
   `0012_conversation_summaries -> 0013_semantic_memory_index -> 0012 ->
   0013`, plus the broader database lifecycle where relevant.

7. Clean up only project-owned resources:

   ```bash
   docker compose down
   # use -v only when the validator explicitly owns disposable validation data
   docker compose ps
   ```

   The final `docker compose ps` must show no remaining project service when
   the validator claims cleanup. Do not delete unrelated containers, volumes,
   databases, or user data.

## 8. Coding Rules

- Never implement a feature while producing a documentation-only handoff.
- Never modify runtime code, create migrations, commit, or push unless the
  user separately authorizes that work.
- Never renumber SPECs or migrations. Never renumber ADRs.
- Treat `docs/product`, `docs/ARCHITECTURE.md`, decisions, code, tests, and
  runtime observations as repository authority; do not revive stale plan text.
- Before introducing externally observable policy, identify its authoritative
  product/design/decision source. Stop if materially different choices remain.
- Keep domain/application layers free of framework, provider, Telegram, Redis,
  Qdrant, and database-client dependencies.
- Normalize and validate external input at the adapter/interface boundary.
- Use typed ports and adapters; never leak ORM models, provider JSON, raw
  Telegram payloads, credentials, or platform IDs into inner policy layers.
- No fake implementation, placeholder behavior, speculative empty module,
  or TODO-based acceptance. Every claimed feature needs executable or
  observable proof.
- Privacy first: enforce exact scope, physical redaction, retention deadlines,
  privacy revisions, and no private-to-group leakage.
- Fail closed before provider or Telegram I/O when safety, required rate
  coordination, concurrency coordination, current authorization, or current
  privacy state cannot be verified.
- Do not claim exactly-once model generation or Telegram delivery across crash
  boundaries. Make idempotency and ambiguous outcomes explicit.
- Keep durable transactions short. Never hold PostgreSQL locks or transactions
  across provider, embedding, Qdrant, or Telegram network calls.
- Keep Qdrant derived and rebuildable. PostgreSQL remains authoritative for
  canonical memory text, lifecycle, scope, and deletion.
- Semantic payloads, metrics, logs, recovery rows, and inspector output must
  remain content-free and bounded. Never use raw memory IDs, query text,
  vectors, message text, provider bodies, or credentials as labels.
- Preserve default-off behavior for Telegram, LLM, outbound delivery,
  summaries, ambient participation, and semantic memory unless an explicit
  operator configuration enables them.
- Use bounded retries/backoff and leases; make replay safe and quarantine
  ambiguous external effects.
- Prefer focused tests plus the relevant integration validator, then the full
  canonical validator and Docker sequence. Report unattempted or weak proof
  instead of overstating completion.
- Do not use optional SQLite/Harness intake, story, trace, scoring, audit, or
  proposal commands unless explicitly requested or required by an external
  orchestrator.
