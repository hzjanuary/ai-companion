# Backend

The January backend is a Python 3.12 FastAPI application factory with
PostgreSQL persistence and a Redis Streams ingress foundation.

Run locally from the repository root:

```bash
uv run uvicorn app.main:app --app-dir backend --reload
```

Run `./scripts/validate.sh` from a normal shell after installing `uv`. It uses
`uv` from `PATH`, with `.tools/uv` as an optional repository-local fallback.

## Database

PostgreSQL 16 is the persistence runtime. Start it with `docker compose up -d
database`, then apply the reviewed schema with `uv run alembic upgrade head`.
Use `uv run alembic downgrade base` only for local validation; reapply with
`uv run alembic upgrade head`.

`/live` checks only the process. `/ready` performs bounded PostgreSQL and
Alembic-schema checks, plus Redis when Telegram delivery is enabled. `/health`
reports application, database, and Redis component states.

## Telegram Adapter

Telegram is disabled by default. The typed adapter implements `getMe`,
`sendMessage`, `sendSticker`, `getChatMember`, `getUpdates`, `setWebhook`,
`deleteWebhook`, and `getWebhookInfo`. Webhook and polling share a durable
PostgreSQL inbox/outbox, then publish typed references to Redis Streams.

Run PostgreSQL/Redis ingress proof with:

```bash
JANUARY_DB_HOST_PORT=5433 JANUARY_REDIS_HOST_PORT=6380 ./scripts/validate-ingress.sh
```

Run polling and dispatch only as dedicated processes: `uv run python -m
app.runtime.telegram_poller` and `uv run python -m
app.runtime.ingress_outbox_dispatcher`. Explicit webhook operations use
`./scripts/telegram-webhook.sh`; none run during API startup.

## Conversation Worker

The worker consumes durable ingress references into normalized conversations,
participants, messages, membership state, deterministic eligibility, and
bounded context. It does not call an LLM or send messages. Start it only as a
dedicated process after PostgreSQL and Redis are ready:

```bash
uv run python -m app.runtime.conversation_worker
```

Run its synthetic PostgreSQL/Redis proof with:

```bash
JANUARY_DB_HOST_PORT=5433 JANUARY_REDIS_HOST_PORT=6380 ./scripts/validate-conversation.sh
```

The worker commits business state and its idempotency ledger before it
acknowledges Redis. It logs identifiers and outcomes, not message content.

## Response Planning

LLM integration is disabled by default. When explicitly enabled, the planning
worker uses configured OpenAI, Gemini, Groq, OpenRouter, or local Ollama models
through typed HTTP adapters. It stores validated platform-independent response
plans only; it does not send Telegram messages.

```bash
uv run python -m app.runtime.response_planning_worker
JANUARY_DB_HOST_PORT=5433 JANUARY_REDIS_HOST_PORT=6380 ./scripts/validate-planning.sh
```

Provider keys are `SecretStr` settings and are never required for canonical
validation. Model capability declarations determine whether JSON Schema output
is requested; local schema and policy validation remains mandatory.

## Safety And Rate Limits

`response-plan-v2` carries closed interaction metadata and is checked against
current context, opt-outs, privacy deletion, and personality boundaries before
provider and Telegram I/O. `safety-policy-v1` has hard boundaries and no roast
mode; it is structural enforcement, not comprehensive semantic moderation.
When `JANUARY_RATE_LIMIT_ENABLED=true`, Redis atomically coordinates generation
and delivery budgets. Redis loss fails closed for external I/O, while durable
work retries and database-only privacy/admin commands continue. Run the
synthetic policy and datastore proof with:

```bash
JANUARY_DB_HOST_PORT=5433 JANUARY_REDIS_HOST_PORT=6380 ./scripts/validate-safety.sh
```

Every response includes `X-Request-ID`. A syntactically valid incoming value is
preserved; otherwise one is generated. Unhandled failures return a safe JSON
error with the same request ID.

## Personality Configuration

SPEC-009 keeps personality as typed, immutable profile versions and applies
conversation-specific immutable revisions. New conversations reconcile to the
Assistant's `January Default` profile with `mention_only` mode and stickers
disabled by default. Planning jobs snapshot the selected profile version and
configuration revision in their creation transaction; the planning worker uses
that snapshot deterministically, while checking the current revision before
provider I/O. A newly paused configuration therefore blocks new and claimed
planning work. The outbound worker rechecks current sticker enablement before
Telegram I/O and skips stale sticker actions when disabled.

Use the local-only CLI documented in
[`docs/runbooks/group-configuration.md`](../docs/runbooks/group-configuration.md).
It has no public HTTP or Telegram administration path. Full prompts and
operator-provided free-form instructions are intentionally unsupported.

## Outbound Delivery

Response planning does not send directly. The optional outbound worker leases
durable actions and is disabled unless `JANUARY_OUTBOUND_DELIVERY_ENABLED=true`.
Run it separately with `uv run python -m app.runtime.outbound_delivery_worker`.
Known Telegram rejections are bounded retries; timeout, network, and malformed
post-send outcomes are terminal `delivery_unknown` to avoid automatic duplicate
sends. `./scripts/validate-delivery.sh` is synthetic and does not call Telegram.

## Dedicated Demo

The optional end-to-end demo is a polling-only workflow for one dedicated test
bot and explicit numeric chat allowlist. It is disabled by default. Create the
ignored local configuration and check it before any live operation:

```bash
./scripts/january-demo.sh init
# Edit .env.demo with a dedicated test bot, provider/model, and test chat IDs.
./scripts/january-demo.sh doctor
./scripts/january-demo.sh bootstrap --confirm-live-telegram
./scripts/january-demo.sh up --confirm-live-demo
```

`bootstrap` makes the only identity-verification Telegram request and requires
explicit confirmation. The allowlist is enforced before conversation processing
and again before outbound delivery. `./scripts/validate-demo.sh` is synthetic:
it uses fake adapters and local PostgreSQL/Redis only.

## Explicit Memory, Privacy, and Retention

Memory is explicit-only and scoped to the exact conversation. The command
worker never invokes a model provider for memory/privacy commands. `/forget_me`
warns without mutation; only `/forget_me confirm` erases/anonymizes January's
primary-database state. Deleted memory and redacted raw content are physically
cleared while technical tombstones remain.

```bash
JANUARY_RETENTION_WORKER_ENABLED=true uv run python -m app.runtime.retention_worker --once
JANUARY_DB_HOST_PORT=5433 JANUARY_REDIS_HOST_PORT=6380 ./scripts/validate-memory.sh
```

The dedicated worker uses PostgreSQL only, applies a maximum 30-day raw-content
limit in bounded batches, and never calls Telegram or an LLM.
# Backend

## Observability

Operational telemetry is disabled by default. Set `JANUARY_METRICS_ENABLED=true`
and `JANUARY_METRICS_EXPORT_ENABLED=true` to start the local loopback-only
Prometheus-text exporter on `JANUARY_METRICS_BIND_HOST` and
`JANUARY_METRICS_PORT` (defaults: `127.0.0.1:9464`). See
`docs/runbooks/observability.md`; no metrics endpoint is exposed by the API.
