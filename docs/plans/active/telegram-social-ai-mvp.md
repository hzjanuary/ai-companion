# Execution Plan: Telegram Social AI MVP

Date: 2026-07-29

## Status

Active: SPEC-015 Telegram observability track. SPEC-014 is `DEFERRED /
BLOCKED_ON_EXTERNAL_PREREQUISITE` and is not the active project blocker.

## Outcome

Deliver the January Telegram social-AI MVP in ordered specifications while
preserving the product contract and architecture boundaries.

## Context

The canonical product contract is `docs/product/SPEC.md`. Architecture and
lasting bootstrap choices are in `docs/ARCHITECTURE.md` and ADR 0001.

## Scope

In scope:

- Track the ordered MVP implementation and validation evidence.

Out of scope:

- Marking the full Telegram MVP complete before its later specifications.

## Approach

1. Establish a runnable, tested backend foundation in SPEC-001.
2. Add persistence only under SPEC-002.
3. Add Telegram and conversation behavior in subsequent approved SPECs.

## Risks And Recovery

- Future integrations must not pull SDKs into inner layers. Review imports and
  ADR 0001 before adding adapters.
- Bootstrap failures can be recovered by removing only local runtime artifacts
  and rerunning the documented validation command.

## Progress

- [x] SPEC-001: repository authority and Harness status inspected; FastAPI
  foundation, documentation, CI, and container artifacts added.
- [x] SPEC-001: Python 3.12 validation passed: 10 pytest tests, Ruff lint and
  formatting checks, mypy, Harness status and doctor, and `git diff --check`.
- [x] SPEC-001: Docker image built, Compose configuration validated, and the
  backend ran through Compose on host port 8002 because port 8000 was occupied.
  `GET /`, `/health`, `/live`, `/ready`, and `/docs` each returned HTTP 200;
  the four JSON endpoints returned `{"service":"January","status":"ok"}`.
- [x] SPEC-001: validation entrypoint resolves `uv` from `PATH` first, then
  `.tools/uv`, and otherwise fails with a concise setup message. Resolution
  behavior and the canonical command passed from a normal shell without a
  `.tools` PATH mutation.
- [x] SPEC-002: PostgreSQL 16, SQLAlchemy async, asyncpg, Alembic, UUID/UTC
  primitives, JSONB metadata, core models, repository ports, and initial
  migration implemented.
- [x] SPEC-002: `validate-db.sh` upgraded, integration-tested, downgraded, and
  re-upgraded the project PostgreSQL database. Docker Compose runtime verified
  healthy endpoints and controlled database-readiness failure.
- [x] SPEC-003: typed, lifecycle-managed Telegram HTTP adapter implements
  getMe, sendMessage, sendSticker, and getChatMember with mock-transport proof;
  update delivery remains deferred.
- [x] SPEC-003: normal validation passed 32 no-network tests and database
  validation passed its migration lifecycle and two PostgreSQL integration
  tests. Compose ran with Telegram disabled; all required HTTP endpoints
  returned 200.
- [x] SPEC-004: added mutually exclusive Telegram webhook/polling delivery,
  typed update parsing, transactional PostgreSQL inbox/outbox and cursor, Redis
  Streams reference events, and dedicated poller/dispatcher runtimes.
- [x] SPEC-004: real PostgreSQL/Redis validation migrated to
  `0002_telegram_ingress` and passed webhook idempotency, outbox publication,
  Stream acknowledgement/reclaim, and polling cursor tests without Telegram
  credentials or public network calls.
- [x] SPEC-005: normalized Telegram messages and membership events into typed
  conversation state, participants, messages, deterministic eligibility, and a
  PostgreSQL processing ledger before Redis acknowledgement.
- [x] SPEC-005: added bounded same-conversation/topic context selection,
  dedicated consumer runtime, migration `0003_conversation_domain`, pure and
  PostgreSQL/Redis integration tests, documentation, and CI coverage without
  Telegram, LLM, or outgoing-message calls.
- [x] SPEC-006: provider-neutral structured response planning adds migration
  `0004_response_planning`, transactional eligible-job handoff, PostgreSQL
  leases, durable attempts/plans, strict local policy, direct typed provider
  adapters, bounded retry/correction/fallback, and a synthetic no-network
  worker proof. It does not send Telegram actions.
- [x] SPEC-007: migration `0005_outbound_delivery`, transactional response-plan
  handoff, ordered PostgreSQL action leases and attempts, typed Telegram
  rendering, confirmed outgoing-message persistence, terminal ambiguous-send
  policy, explicit recovery audit, and an optional disabled sender runtime.
- [x] SPEC-008: guarded polling-only local demo provides settings/template,
  inbound and outbound allowlist suppression, idempotent bootstrap, discovery,
  doctor, process lifecycle commands, durable inspection, CI, and synthetic
  pipeline proof. Dedicated-bot/provider operation remains an explicit
  operator-owned manual acceptance step and is not CI evidence.
- [x] SPEC-009: added immutable typed profile versions and per-conversation
  configuration revisions in migration `0006_personality_config`, idempotent
  default/reconciliation services, job snapshots, deterministic prompt/policy
  integration, safe local operator CLI, inspector summaries, and a focused ADR
  and runbooks. Validation passed 86 no-network tests, every prior database,
  ingress, conversation, planning, delivery, and demo validator, plus
  `validate-personality.sh` with migration upgrade/downgrade/re-upgrade and
  fake adapters only. The synthetic flow proves snapshot persistence after a
  newer revision, conversation isolation, pause suppression, replay safety, and
  stale sticker suppression. `january-backend:spec-009` built; after applying
  `0006` to an isolated Compose PostgreSQL instance on port 5434, `/`,
  `/health`, `/live`, `/ready`, and `/docs` returned HTTP 200 on port 8009.
- [x] SPEC-011: explicit-memory, privacy, and retention foundation adds typed
  explicit-memory contracts, migration `0008_memory_privacy_retention`, scoped
  context, deterministic command paths, privacy tombstones, a 30-day
  terminal-content retention worker, focused documentation, CI coverage, and a
  dedicated validator. PostgreSQL/Redis lifecycle, migration downgrade/re-upgrade,
  prior-spec regressions, image build, Compose runtime, and safe readiness-failure
  proof passed without a Telegram token or provider request.
- [x] SPEC-012: added `safety-policy-v1`, `response-plan-v2` structural
  interaction metadata, deterministic hard-boundary fallback, and current
  mention/teasing/privacy rechecks before provider and Telegram I/O.
- [x] SPEC-012: migration `0009_safety_rate_limiting` persists content-free
  safety decisions and limiter events. Atomic Redis fixed-window coordination
  enforces generation deployment/connection/conversation/participant/provider
  scopes and delivery deployment/connection/conversation scopes. Enabled Redis
  failure fails closed and retryable work is released without external I/O;
  database-only commands retain their generation-quota exemption.
- [x] SPEC-013: official-source-only Zalo OA/GMF feasibility spike completed
  without runtime code, credentials, migration, or external mutation. The
  durable decision is `BLOCKED_PENDING_OFFICIAL_VERIFICATION`: an OA direct
  assistant may be a narrower future scope, GMF requires test-OA verification,
  and ordinary private friend-group parity is not established.
- [x] SPEC-014 Phase 1: added redacted, no-network operator-verification
  artifacts, ignored local-secret boundary, static validator, and CI check.
  Its credentialed live verification is `DEFERRED /
  BLOCKED_ON_EXTERNAL_PREREQUISITE` until an operator confirms a dedicated
  nonproduction OA/app environment and explicitly approves each external gate.
  This Zalo-only dependency is outside the Telegram MVP critical path.
- [x] SPEC-015: Telegram MVP observability and operational telemetry completed.
  Preserve all prior behavior while adding only content-safe, bounded telemetry;
  no migration, Zalo runtime, or SPEC-016 scope is permitted.
- [ ] Later MVP specifications.

## Decisions

- 2026-07-29: Use `uv` with `pyproject.toml`; no prior dependency manager was
  selected.
- 2026-07-29: Keep only current runtime and HTTP-interface modules in
  SPEC-001; the product contract prohibits empty future folders.
- 2026-07-29: Keep `uv` as the dependency manager while making the validation
  entrypoint discover an optional repository-local `uv` executable.
- 2026-07-29: Use PostgreSQL 16 with SQLAlchemy async, asyncpg, Alembic, UUID
  primary keys, UTC timestamps, JSONB metadata, and constrained string enums;
  persist these rules in ADR 0002.
- 2026-07-29: Use direct httpx Bot API calls with typed contracts, explicit
  client ownership, token redaction, and no automatic outbound retries.
- 2026-07-29: Make Telegram ingress at-least-once through a PostgreSQL durable
  inbox/outbox and Redis Streams; downstream work must deduplicate by stable
  incoming update ID. Keep webhook lifecycle, polling, and dispatch explicit
  separate runtimes.
- 2026-07-29: Keep conversation business processing idempotent through a
  PostgreSQL ledger keyed by durable incoming update ID. Normalize external
  Telegram data at the infrastructure boundary and acknowledge Redis only after
  the transaction commits; record deterministic eligibility before future model
  work.
- 2026-07-29: Use direct typed provider HTTP adapters and local strict plan
  validation. PostgreSQL leasing owns durable planning coordination; model I/O
  remains outside claim transactions and does not imply exactly-once generation.

## Validation

- 2026-08-01 SPEC-011 final evidence: `./scripts/validate.sh` passed 136
  selected no-network tests, Ruff lint/format, strict mypy, Harness checks, and
  `git diff --check`. `validate-memory.sh` passed 7 focused unit/context tests,
  3 PostgreSQL schema/behavior tests covering conversation and connection
  isolation, profile erasure, content-free inspector output, exact-cutoff
  retention, idempotence, and migration downgrade/re-upgrade. `validate-db.sh`
  passed 22 PostgreSQL tests and a full downgrade-to-base/re-upgrade lifecycle.
  Ingress (6), conversation (3), planning (1), delivery (5 unit, 16 adapter,
  7 integration), personality (22 lifecycle, 4 unit, 2 integration), and
  commands (37 unit, 14 integration) validators passed. Docker built
  `january-backend:spec-011`; Compose configuration passed; after migration
  `0008`, `/`, `/health`, `/live`, `/ready`, and `/docs` returned HTTP 200 on
  port 8011. Stopping only PostgreSQL produced `/ready` HTTP 503 with safe JSON
  and a request ID; `docker compose down` removed project services and network.
- 2026-08-01 SPEC-011 current evidence: `./scripts/validate.sh` passed 136
  selected no-network tests, Ruff lint/format, strict mypy, Harness checks, and
  `git diff --check`. `validate-db.sh` upgraded through `0008`, passed 20
  PostgreSQL integration tests, downgraded to base, and re-upgraded. The
  dedicated `validate-memory.sh` passed its focused tests, migration schema
  proof, downgrade to `0007`, and re-upgrade. `january-backend:spec-011` built;
  Compose configuration passed; with migration `0008` applied, `/`, `/health`,
  `/live`, `/ready`, and `/docs` returned HTTP 200 on port 8011. After stopping
  only the database service, `/ready` returned safe HTTP 503 with a request ID;
  `docker compose down` left `docker compose ps` empty.
- 2026-08-01 regression evidence: ingress (6), conversation (3), planning (1),
  delivery (7 integration plus 21 focused tests), personality (20 migration
  lifecycle integrations, 4 unit, and 2 focused integrations), and commands
  (37 unit plus 14 command integrations) all passed against project-owned
  PostgreSQL/Redis with no real Telegram or provider request. The personality
  validator now asserts service readiness after its nested database lifecycle.
- 2026-08-01 SPEC-012 final evidence: `./scripts/validate.sh` passed 145
  selected no-network tests, Ruff lint/format, strict mypy, Harness checks, and
  `git diff --check`. Database (22), ingress (6), conversation, planning,
  delivery, demo, personality, command, and memory validators completed against
  project PostgreSQL/Redis without credentials or public calls. The dedicated
  safety validator passed 6 unit tests and the PostgreSQL/Redis integration
  proof: schema `0009`, all limiter scopes, concurrent final-token atomicity,
  expiry, content-free Redis keys/values, synthetic fail-closed outage, and
  `0008 -> 0009 -> 0008 -> 0009`. `january-backend:spec-012` built and Compose
  configuration passed. On isolated ports 8012/5434/6381, migration `0009`
  applied and `/`, `/health`, `/live`, `/ready`, and `/docs` returned HTTP 200.
  With the limiter enabled, stopping Redis and PostgreSQL separately produced
  safe request-ID-bearing `/ready` 503 responses, and readiness returned 200
  after each restart. No real Telegram or provider I/O occurred.
- 2026-08-01 SPEC-012 follow-up audit: provider capacity is checked immediately
  before every selected provider, including a fallback, with a focused fake
  provider proof that denial creates no provider I/O or attempt record. Successful
  post-generation decisions now retain their persisted response-plan ID.
- 2026-08-01 SPEC-013 evidence: public official Zalo Developers/OA sources were
  registered with access state and caveats. `validate-zalo-feasibility.sh`
  validates every required capability, source reference, enum, baseline SHA,
  credential guard, and absence of runtime/migration scope changes without
  network access. Manual OA/app/GMF verification was documented and not run.
- 2026-08-01 SPEC-013 validation: `./scripts/validate.sh` passed 145 selected
  no-network tests with Ruff, formatting, strict mypy, Harness, and diff checks.
  `./scripts/validate-zalo-feasibility.sh` passed the official-source register,
  every required capability ID, closed evidence/product-fit enums, source
  resolution, baseline checkpoint, credential guard, and runtime-scope guard.
- 2026-08-01 SPEC-014 Phase 1 evidence: current public OA documentation and
  news index were rechecked; a 30/07/2026 product-update listing did not alter
  the SPEC-013 conclusion. The canonical results file records every live check
  as `NOT_RUN`; no credentials, authenticated request, OA/app/GMF mutation,
  webhook registration, or Zalo message occurred. The next state is
  `OPERATOR_ZALO_TEST_ENVIRONMENT_REQUIRED`.
- 2026-08-01 SPEC-014 operator update: no dedicated nonproduction Zalo OA/app
  is available. Personal Zalo accounts may only be future test participants and
  are explicitly prohibited as January runtime identity. Credentialed OA,
  webhook, direct-message, GMF, and commercial checks remain `NOT_RUN`; manual
  consumer-app observation cannot promote private-group API capability.
- 2026-08-01 SPEC-014 roadmap decision: the gate is
  `DEFERRED / BLOCKED_ON_EXTERNAL_PREREQUISITE`, not the active Telegram MVP
  blocker. `./scripts/validate.sh` passed 145 selected no-network tests, Ruff,
  strict mypy, Harness, and diff checks; `./scripts/validate-zalo-feasibility.sh`
  and `./scripts/validate-zalo-verification.sh` both passed. The next reserved
  implementation number is SPEC-015 for Telegram/product work only, with scope
  pending product-contract acceptance.
- 2026-08-01 SPEC-015 evidence: added an application `MetricsRecorder` port,
  no-op and isolated in-memory registry implementations, Prometheus-compatible
  loopback exporter, typed JSON operational-event helper, request/correlation
  contexts, bounded metric definitions, optional operator-configured cost rates,
  and HTTP/ingress/conversation/planning/outbound instrumentation. No migration
  was added. `./scripts/validate.sh` passed 150 selected no-network tests;
  database (22), ingress (6), conversation (3), planning (1), delivery (7),
  demo (5), personality (2 plus lifecycle), commands (14), memory (3), safety
  (1), Zalo feasibility, Zalo verification, and
  `./scripts/validate-observability.sh` all passed. Docker built
  `january-backend:spec-015`; isolated Compose returned 200 for `/`, `/health`,
  `/live`, `/ready`, and `/docs`. Explicit loopback metrics export contained the
  `january_` families after synthetic HTTP requests and no fixture content or
  credentials. Stopping Redis and PostgreSQL independently produced safe 503
  readiness responses with request IDs; both recovered; Compose resources were
  stopped afterwards. No real Telegram/provider call occurred.

- 2026-07-30 SPEC-001 validation-entrypoint follow-up: from a clean shell
  without a `.tools` PATH mutation, `./scripts/validate.sh` passed 116 selected
  no-network tests, Ruff lint and format checks, strict mypy, Harness status
  and doctor, and `git diff --check`. `scripts/test-resolve-uv.sh` passed its
  PATH-preference, repository-local fallback, and missing-tool checks. `docker
  build --tag january-backend:spec-001 .` and `docker compose config` passed.
- Focused proof: `pytest` passed 10 tests covering settings, OpenAPI, all
  operational endpoints, request IDs, request-local state, safe errors, and
  normal HTTP errors.
- Integration or end-to-end proof: `JANUARY_HOST_PORT=8002 docker compose up
  --build --detach backend`; all required endpoints returned HTTP 200.
- Repository-required checks: `./scripts/validate.sh` passed with Python 3.12
  and a local `uv` installation; Docker image build and `docker compose config`
  passed. `scripts/test-resolve-uv.sh` covers PATH preference, local fallback,
  and missing-tool failure.
- SPEC-002 proof: `JANUARY_DB_HOST_PORT=5433 ./scripts/validate-db.sh` passed
  PostgreSQL migration upgrade, two integration tests, downgrade to base, and
  re-upgrade. Compose runtime returned 200 for all required endpoints; after
  stopping only its database service, `/ready` returned a safe 503 response.
- SPEC-003 proof: `pytest backend/tests/test_telegram_adapter.py -q` passed 15
  mock-transport tests; `./scripts/validate.sh` passed 32 tests and static
  gates; `verify-telegram.sh` safely rejected missing configuration.
- SPEC-004 proof: `./scripts/validate.sh` passed 47 no-network tests, Ruff,
  mypy, Harness status/doctor, and `git diff --check`; `JANUARY_DB_HOST_PORT=5433
  ./scripts/validate-db.sh` passed 2 PostgreSQL integration tests plus downgrade
  and re-upgrade; `JANUARY_DB_HOST_PORT=5433 JANUARY_REDIS_HOST_PORT=6380
  ./scripts/validate-ingress.sh` passed 3 PostgreSQL/Redis integration tests.
- SPEC-004 runtime proof: `docker build --tag january-backend:spec-004 .` and
  `docker compose config` passed. The normal Compose stack returned HTTP 200 for
  `/`, `/health`, `/live`, `/ready`, and `/docs`; controlled database and
  enabled-queue Redis failures returned safe `/ready` HTTP 503 responses. No
  Telegram credential, webhook, or public Telegram call was used.
- SPEC-005 focused proof: 30 settings, normalization, eligibility, and context
  tests passed with Ruff and strict mypy. PostgreSQL/Redis ingress validation
  migrated to `0003_conversation_domain` and passed the durable conversation
  worker, duplicate acknowledgement, pending reclaim, ingress, webhook,
  polling, and reclaim tests without credentials or external network calls.
- SPEC-005 runtime proof: `docker build --tag january-backend:spec-005 .` and
  `docker compose config` passed. After applying migration `0003` to an
  isolated Compose PostgreSQL service, `/`, `/health`, `/live`, `/ready`, and
  `/docs` each returned HTTP 200 on host port 8003; only project-owned services
  were stopped afterward.
- SPEC-006 current proof: `./scripts/validate.sh` passed 73 no-network tests,
  Ruff, strict mypy, Harness, and diff checks. Database, ingress, conversation,
  and planning validators passed through `0004_response_planning`. Direct
  provider mock transports cover OpenAI, Gemini, Groq, OpenRouter, and Ollama;
  deterministic retry/correction/fallback and refusal tests pass. The disabled
  LLM Compose stack built as `january-backend:spec-006` and `/`, `/health`,
  `/live`, `/ready`, and `/docs` returned HTTP 200 on isolated port 8004.
- SPEC-007 proof: `./scripts/validate.sh` passed 79 no-network tests, Ruff,
  strict mypy, Harness, and diff checks. `validate-db.sh` downgraded to base and
  re-upgraded through `0005_outbound_delivery`; ingress, conversation, planning,
  and delivery validators passed using only PostgreSQL/Redis and fake adapters.
  Docker built `january-backend:spec-007`; the disabled stack returned 200 for
  `/`, `/health`, `/live`, `/ready`, and `/docs`, and a stopped database yielded
  safe `/ready` 503 output. No public Telegram or model call occurred.
- SPEC-008 current proof: `./scripts/validate.sh` passed 81 no-network tests,
  Ruff lint/format, strict mypy, Harness checks, and `git diff --check`.
  `JANUARY_DB_HOST_PORT=5433 JANUARY_REDIS_HOST_PORT=6380
  ./scripts/validate-demo.sh` passed 22 settings tests and five dedicated
  PostgreSQL/Redis integration tests: fake-identity bootstrap idempotency and
  mismatch rejection, ingress-to-confirmed-delivery pipeline, replay
  idempotency, denied chat suppression, and polling webhook conflict. The
  accepted database, ingress, conversation, planning, and delivery validators
  also passed. Docker built `january-backend:spec-008`; the isolated disabled
  Compose runtime returned 200 for `/`, `/health`, `/live`, `/ready`, and
  `/docs`, then was removed. No Telegram identity, update, send, or provider
  call was made.
- SPEC-009 proof: `./scripts/validate.sh` passed 86 no-network tests, Ruff,
  strict mypy, Harness, and diff checks. `validate-db.sh` and
  `validate-personality.sh` exercised migration `0006_personality_config`
  through upgrade, downgrade-to-base, and re-upgrade. Ingress/planning tests
  prove immutable job snapshots survive later configuration changes and paused
  revisions create no new job; delivery tests prove a newer disabled-sticker
  revision skips queued sticker work before adapter I/O. All prior validators
  passed against only project PostgreSQL/Redis and fake adapters. Docker built
  `january-backend:spec-009`; isolated Compose with migration `0006` returned
  200 for `/`, `/health`, `/live`, `/ready`, and `/docs`. No credential or
  public Telegram/provider call occurred.

## Result

SPEC-001 through SPEC-010 are implemented. SPEC-011 explicit-memory/privacy
work is in progress: typed memory contracts, `0008_memory_privacy_retention`,
conversation-scoped memory/audit models, content-redaction markers, and a
scoped idempotent repository are present. The memory command grammar is typed
and safely isolated pending transactional command-worker execution. Docker is
currently inaccessible for migration lifecycle validation. SPEC-010 command parsing, durable
job handoff, response-plan XOR, preference-event schema, separate command
worker, demo lifecycle wiring, and a PostgreSQL/Redis command validator are in
progress. Current evidence: `validate.sh` passed 118 selected no-network tests;
the command validator now passes 30 parser/grammar tests and 14 PostgreSQL/Redis
proofs for durable ingress handoff, authorization allow/deny and retry recovery,
private preference and configuration isolation, replay prevention, accepted
outbound delivery, `/resume` restoration/no-op, authorization-time configuration
conflict/no-op handling, atomic preference no-op detection, and Assistant-scoped
personality resolution, and worker-level profile/sticker mutations, no-ops, and
unavailable-mapping rejection, and bounded `/personality list` output.
`validate-db.sh`, ingress,
conversation, planning, delivery, demo, and personality validators also passed
locally; migration `0007_telegram_commands` upgraded, downgraded, and
re-upgraded. This plan remains active for the
Telegram MVP; later product behavior remains unimplemented.
