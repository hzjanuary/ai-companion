# SPEC-022 Implementation Handoff

## Status

PARTIALLY COMPLETE

SPEC-022 has a repository-safe implementation of the explicit Telegram
connection, webhook, and mode-exclusivity operations and the content-safe live
acceptance evidence bundle, with deterministic synthetic proof and full
Docker-backed local validation. It remains PARTIALLY COMPLETE because live
Telegram acceptance is externally blocked: no approved staging bot, bot token,
public HTTPS URL, or dedicated test group exists, so no live `getMe`, webhook,
polling, or production cutover run was performed. The host's default Docker
SELinux labeling profile also still terminates containers with code 139, so
Docker validation used a temporary host-only `label=disable` override that was
removed after validation and is not a repository or production configuration.

## 1. Executive Summary

SPEC-022 is the production-integration and live-acceptance phase for the
existing Telegram runtime. This implementation added operator-facing,
fail-closed lifecycle operations and a metadata-only evidence builder that make
the SPEC-022 acceptance criteria observable and auditable without changing the
durable ingress, planning, delivery, safety, privacy, recovery, deployment, or
control-plane boundaries:

- `verify`: pre-traffic bot identity verification (`getMe`) against the approved
  connection record plus webhook-state and mode-exclusivity inspection (FR-01).
- `webhook-inspect` / `webhook-register` / `webhook-delete`: explicit webhook
  lifecycle that re-verifies identity, registers the approved HTTPS URL with the
  configured secret and allowed update set, then re-reads Telegram state and
  fails closed on any URL or update-set mismatch.
- `mode-verify`: proves exactly one ingress mode (`disabled`, `webhook`, or
  `polling`) is active; exits non-zero on any conflict.
- `acceptance_evidence collect`: builds a content-safe evidence bundle
  (environment, connection, redacted identity, webhook state, mode exclusivity,
  timestamps, result classification, health/readiness, worker lifecycle,
  duplicate/retry outcomes, cleanup, owners). A content-safety guard rejects
  forbidden keys and credential-shaped strings on every bundle before emission.

Every command requires the explicit `--confirm-live-telegram` gate and never
prints the bot token or webhook secret. API startup remains free of webhook
registration, replacement, deletion, or polling-fallback side effects. All local
proof uses fake adapters only; live Telegram I/O is the remaining external
blocker.

One non-feature validation fix was required: SPEC-021 added migration
`0014_authenticated_control_plane` but left three schema-pin integration tests
asserting head `0013_semantic_memory_index`. At the committed head those tests
failed. They were updated to assert the actual head
`0014_authenticated_control_plane` (the same class of documented non-feature fix
as the SPEC-021 `compose.staging.yaml` Redis wiring repair).

## 2. Repository Baseline

- Baseline HEAD: `4c01cb30493fdabb26cf7b484120832ea40577ef`
  (`feat(spec-021): implement authenticated operator control plane`).
- `origin/main` matches the baseline commit.
- No commit or push was performed.
- The worktree contains the SPEC-022 product-document and documentation-index
  changes plus the implementation, tests, runbook, validator, and this handoff.
- SPEC-021 remains the preceding control-plane boundary; its external
  Docker/identity-provider validation gaps were not bypassed.

## 3. Implemented

### `backend/app/runtime/telegram_connection_operations.py` (380 lines)

- `expected_webhook_url`: derives the approved webhook URL from the public base
  URL, path, and connection ID; fails when configuration is incomplete.
- `identity_evidence` / `webhook_evidence`: redacted metadata only; never the
  token or secret.
- `ModeExclusivity` / `assess_exclusivity`: single-source-of-truth ingress mode
  assessment; a configured `webhook` with no active webhook, a webhook URL not
  matching the approved configuration, or any active webhook while not in
  `webhook` mode is recorded as inconsistent.
- `verify_connection`: requires `telegram_enabled`, a configured connection ID,
  and `getMe` confirming a bot account whose ID matches the approved connection
  record; inspects `getWebhookInfo` and appends mode-exclusivity observations.
- `register_webhook`: requires `telegram_delivery_mode=webhook` and a secret,
  re-runs connection readiness, registers the URL/secret/allowed updates, then
  re-reads Telegram state and fails closed unless the confirmed URL and update
  set match the approved configuration.
- `delete_webhook`: deletes and re-reads Telegram state, failing closed if a
  webhook is still configured; supports `drop_pending_updates`.
- `mode_verify`: returns exclusivity evidence and exits non-zero on conflict.
- `load_approved_bot_id`: reads the approved bot ID from the durable connection
  record (PostgreSQL) so identity is checked against approved state, not only
  against configuration.
- CLI subcommands `verify`, `webhook-inspect`, `webhook-register`,
  `webhook-delete` (requires `--confirm-delete-webhook`, optional
  `--drop-pending-updates`), and `mode-verify`; all require
  `--confirm-live-telegram`, support `--json`, never print the token, and exit
  non-zero with a safe message on any failure.

### `backend/app/runtime/acceptance_evidence.py` (339 lines)

- `FORBIDDEN_EVIDENCE_KEYS`, bot-token and credential-shaped string patterns,
  and `assert_content_safe`: a content-safety guard that runs on every bundle
  and raises on forbidden keys (`authorization`, `token`, `secret_token`,
  `text`, `message`, `content`, `prompt`, `memory`, `vector`, raw payloads, …)
  and on credential-shaped strings.
- `build_evidence`: assembles the schema-versioned bundle with connection,
  redacted bot identity, webhook state, mode exclusivity, observations, result
  classification (`accepted`/`rejected`), timestamps, health/readiness,
  worker lifecycle, duplicate/retry outcomes, cleanup confirmation, and owners.
- `collect_durable_state`: metadata-only counts of ingress/outbox/planning/
  outbound/recovery rows (incoming totals by status, distinct platform updates,
  duplicate ingress, retried outbox events, outbound action statuses, delivery
  certainties) — no message content.
- `collect_health_readiness`: fetches `/health`, `/ready`, `/live` from the
  running service with bounded timeouts.
- CLI `collect` with `--confirm-live-telegram`, `--run-id`, `--operator`,
  `--incident-contact`, `--rollback-authority`, `--test-group`,
  `--confirm-cleanup`, `--no-durable-state`, `--app-base-url`, `--out`.

### Tests (20, fake adapters only)

- `backend/tests/test_telegram_connection_operations.py` (13 tests): identity
  evidence, expected URL, webhook evidence, exclusivity assessment for all mode
  combinations, connection verification pass/fail paths (disabled, missing
  connection, non-bot identity, approved-ID mismatch surfaced into
  `observations`, adapter failure categories), registration preconditions and
  fail-closed confirmations, deletion verification, mode-verify conflicts, and
  CLI confirmation gates.
- `backend/tests/test_acceptance_evidence.py` (7 tests): content-safety guard
  rejection of forbidden keys and credential-shaped strings, bundle shape, and
  classification/cleanup/owner fields.

### Validator and documentation

- `scripts/validate-live-acceptance.sh`: ruff check, ruff format check, mypy on
  the two modules, pytest of the two test files, PASS line.
- `docs/runbooks/live-acceptance.md`: 9-section operator runbook (pre-traffic
  identity verification, webhook lifecycle, polling exclusivity and mode
  transitions, live staging acceptance, failure and recovery drills,
  operational evidence, production cutover, rollback, cleanup).
- `docs/runbooks/local-development.md` and
  `docs/runbooks/production-operations.md`: reference the SPEC-022 verified
  operations and evidence bundle.

## 4. Files Changed

| File | Change |
| --- | --- |
| `backend/app/runtime/telegram_connection_operations.py` | new (380 lines) |
| `backend/app/runtime/acceptance_evidence.py` | new (339 lines) |
| `backend/tests/test_telegram_connection_operations.py` | new (292 lines) |
| `backend/tests/test_acceptance_evidence.py` | new (194 lines) |
| `scripts/validate-live-acceptance.sh` | new (21 lines) |
| `docs/runbooks/live-acceptance.md` | new (181 lines) |
| `docs/product/specs/SPEC-022-telegram-production-integration-and-live-acceptance.md` | new (product spec from the planning phase) |
| `docs/plans/handoff/SPEC-022-HANDOFF.md` | replaced planning-only handoff with this record |
| `docs/product/SPEC.md` | +1 line product index |
| `docs/product/README.md` | +1 line product index |
| `docs/runbooks/local-development.md` | +23 lines SPEC-022 operations reference |
| `docs/runbooks/production-operations.md` | +15/−3 lines SPEC-022 operations/evidence reference |
| `backend/tests/integration/test_safety_schema.py` | 1-line non-feature fix (head assertion) |
| `backend/tests/integration/test_memory_schema.py` | 1-line non-feature fix (head assertion) |
| `backend/tests/integration/test_command_schema.py` | 1-line non-feature fix (head assertion) |

`git diff --stat` for tracked files: 7 files changed, 39 insertions, 7 deletions.

## 5. ADRs

No new lasting architecture decision requires a `docs/decisions/` entry. Every
externally observable policy in this implementation is mandated by the SPEC-022
product specification (explicit operator-invoked lifecycle, exactly one ingress
mode per connection, fail-closed verification, metadata-only evidence, explicit
confirmation gates, no startup side effects). The only deviation from the
planning handoff is the non-feature validation fix described below, which is the
same class of fix previously documented in the SPEC-021 handoff.

## 6. Migrations

None. SPEC-022 created and authorized no migration, and the database schema is
unchanged. The Alembic head remains `0014_authenticated_control_plane`
(SPEC-021), confirmed by `alembic upgrade head` in Docker validation and by the
three schema-pin integration tests.

Non-feature validation fix (not a migration): SPEC-021's migration 0014 left the
three schema-pin integration tests asserting head `0013_semantic_memory_index`,
so they failed at the committed head. Each assertion was updated to
`0014_authenticated_control_plane`. These tests assert the database matches the
current head and their own validators run `alembic upgrade head` before the
tests, so the fix restores the intended check rather than weakening it.

## 7. Validation

- `./scripts/validate.sh` — PASS (exit 0). Ruff, format check, mypy, harness
  checks, and the non-integration suite: 209 passed, 41 deselected.
- `./scripts/validate-live-acceptance.sh` — PASS (exit 0). Ruff check, ruff
  format check, mypy on `telegram_connection_operations.py` and
  `acceptance_evidence.py`, and 20 tests in the two new test files.
- `git diff --check` — passed at the validation points.

## 8. Docker Validation

Host limitation: under the default SELinux labeling profile, minimal containers
(`alpine:3.20 /bin/true`) exit 139; the same command exits 0 with
`--security-opt label=disable`. This matches the SPEC-020/SPEC-021 findings and
is a host/engine defect, not a repository issue. Docker validation therefore
used a temporary uncommitted `compose.override.yaml` containing only
`security_opt: ["label=disable"]` for the project services, with isolated host
ports `JANUARY_DB_HOST_PORT=5433` and `JANUARY_REDIS_HOST_PORT=6380`. The
override was removed after validation; no committed Compose file is weakened.

- `./scripts/validate-ingress.sh` — PASS (exit 0). PostgreSQL and Redis became
  ready under the override; `alembic upgrade head` confirmed head
  `0014_authenticated_control_plane`; the 8 `ingress_integration` tests passed
  (webhook acknowledgement of new and duplicate updates without queue I/O,
  polling cursor advancement and polling refusal while a webhook is configured,
  durable inbox/outbox idempotency, and dispatcher scalability).
- Full `pytest -m integration` at head — 41 passed, 209 deselected. This
  includes the three schema-pin tests after the non-feature fix and all legacy
  PostgreSQL/Redis integration proofs.
- `./scripts/validate-safety.sh` — PASS: 6 unit tests and 2 `safety_integration`.
- `./scripts/validate-memory.sh` — PASS: 8 unit tests and 7 `memory_integration`.
- `./scripts/validate-commands.sh` — PASS: 43 unit tests and 14
  `command_integration`.

Containers were stopped by each validator's cleanup trap; no project-owned
containers, volumes, or the temporary override remain active.

## 9. Runtime Proof

- The new operations are wired to the real `TelegramAdapter` (`verify_identity`
  → `getMe`, `get_webhook_info` → `getWebhookInfo`, `set_webhook`,
  `delete_webhook`) and to the durable connection record for the approved bot
  ID. No API startup path invokes them; every command requires the explicit
  confirmation flag and emits redacted metadata only.
- Local runtime proof is deterministic and uses fake adapters only (the 20 tests
  and the `validate-live-acceptance.sh` PASS line). Live runtime proof against
  Telegram is externally blocked (below); no live run, cutover, or production
  approval was claimed.

## 10. Known Limitations

- Live Telegram `getMe`, webhook, polling, and delivery behavior has not been
  exercised against a real bot; the live adapter path is proven by unit tests
  against fake adapters only.
- The three schema-pin integration tests were stale at the committed head due to
  SPEC-021's migration; the non-feature fix is included in this worktree and
  must be committed with the SPEC-022 change set.
- Docker validation depends on the host-only `label=disable` override; the
  default Docker profile still exits 139 on this host.
- Polling/consumer-group behavior was not re-run at live scale; existing
  SPEC-016 scalability proofs remain the authority.
- The evidence bundle's `/health`, `/ready`, `/live` fetches target
  `--app-base-url`; local evidence captures only the states reachable in a local
  run.

## 11. External Blockers

- Approved staging bot and `JANUARY_TELEGRAM_BOT_TOKEN`; no token exists.
- Public HTTPS webhook URL, TLS certificate, and webhook secret for webhook
  mode.
- Dedicated test group with approved bot membership and verified Privacy Mode /
  allowed update visibility.
- Isolated staging PostgreSQL, Redis, telemetry, and operators.
- Product Owner and operating-owner approval for any live traffic and for
  production cutover.
- Host Docker default-profile repair (SELinux labeling or Docker/runc policy)
  before relying on default-profile validation.

## 12. Remaining Work

- Operator-run live staging acceptance per `docs/runbooks/live-acceptance.md`
  sections 1–6 once the staging resources exist: identity verification, webhook
  registration/inspection/deletion, mode-exclusivity transition, one addressed
  message, one membership/configuration event, and duplicate replay.
- Live failure and recovery drills (section 5) mapped to the existing closed
  classifications.
- Production cutover (section 7) with recorded activation owner, time,
  configuration, and rollback point; rollback rehearsal (section 8); and
  cleanup (section 9).
- Collect and review the content-safe evidence bundle for each live run.

## 13. Production Prerequisites

- Separately owned production bot, token, webhook secret, HTTPS domain/cert,
  PostgreSQL, Redis, group, telemetry, and operating owner.
- Approved connection record with the production bot ID before any traffic.
- Exactly one delivery mode configured and proven via `mode-verify`.
- Migrations run as a separate pre-runtime step; role-specific worker lifecycle
  and alerts per SPEC-020; approved secret boundary; documented rollback point.
- Control-plane membership (SPEC-021) does not grant Telegram
  group-administrator power; Telegram-side permissions remain in the existing
  command-authorization boundary.
- Low-risk acceptance group approval and metadata-only evidence with no secrets
  or product content.

## 14. Exact Commands

Local deterministic validation:

```bash
./scripts/validate-live-acceptance.sh
./scripts/validate.sh
uv run pytest backend/tests/test_telegram_connection_operations.py \
  backend/tests/test_acceptance_evidence.py -q     # 20 passed
```

Docker-backed validation (temporary host-only override, isolated ports):

```bash
# compose.override.yaml with only: services.*.security_opt = ["label=disable"]
JANUARY_DB_HOST_PORT=5433 JANUARY_REDIS_HOST_PORT=6380 ./scripts/validate-ingress.sh
JANUARY_DB_HOST_PORT=5433 JANUARY_REDIS_HOST_PORT=6380 ./scripts/validate-safety.sh
JANUARY_DB_HOST_PORT=5433 JANUARY_REDIS_HOST_PORT=6380 ./scripts/validate-memory.sh
JANUARY_DB_HOST_PORT=5433 JANUARY_REDIS_HOST_PORT=6380 ./scripts/validate-commands.sh
JANUARY_ENVIRONMENT=test JANUARY_DATABASE_HOST=127.0.0.1 \
  JANUARY_DATABASE_PORT=5432 JANUARY_DATABASE_PASSWORD=january-local \
  JANUARY_REDIS_URL=redis://127.0.0.1:6379/0 \
  uv run pytest -m integration -q                  # 41 passed
# then: rm -f compose.override.yaml
```

Live operations (each requires `--confirm-live-telegram`; see the runbook):

```bash
uv run python -m app.runtime.telegram_connection_operations verify \
  --confirm-live-telegram --json
uv run python -m app.runtime.telegram_connection_operations webhook-inspect \
  --confirm-live-telegram --json
uv run python -m app.runtime.telegram_connection_operations webhook-register \
  --confirm-live-telegram --json
uv run python -m app.runtime.telegram_connection_operations webhook-delete \
  --confirm-live-telegram --confirm-delete-webhook --json
uv run python -m app.runtime.telegram_connection_operations mode-verify \
  --confirm-live-telegram --json
uv run python -m app.runtime.acceptance_evidence collect \
  --confirm-live-telegram \
  --operator OPERATOR --incident-contact CONTACT --rollback-authority AUTHORITY \
  --test-group STAGING_GROUP --confirm-cleanup --out evidence.json
```

## 15. git status --short

```
 M backend/tests/integration/test_command_schema.py
 M backend/tests/integration/test_memory_schema.py
 M backend/tests/integration/test_safety_schema.py
 M docs/product/README.md
 M docs/product/SPEC.md
 M docs/runbooks/local-development.md
 M docs/runbooks/production-operations.md
?? backend/app/runtime/acceptance_evidence.py
?? backend/app/runtime/telegram_connection_operations.py
?? backend/tests/test_acceptance_evidence.py
?? backend/tests/test_telegram_connection_operations.py
?? docs/plans/handoff/SPEC-022-HANDOFF.md
?? docs/product/specs/SPEC-022-telegram-production-integration-and-live-acceptance.md
?? docs/runbooks/live-acceptance.md
?? scripts/validate-live-acceptance.sh
```

`compose.override.yaml` is absent (temporary, removed after validation). HEAD
and `origin/main` are both `4c01cb30493fdabb26cf7b484120832ea40577ef`; nothing is
committed or pushed.

## 16. Next Bounded Task

Repair or replace the local Docker database/Redis environment (host SELinux
labeling profile) and complete the operator-owned live staging acceptance in
`docs/runbooks/live-acceptance.md` with an approved staging bot, webhook secret,
HTTPS URL, and test group, collecting the content-safe evidence bundle before
any production cutover decision. Do not start SPEC-023 from this handoff.
