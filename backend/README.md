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

Every response includes `X-Request-ID`. A syntactically valid incoming value is
preserved; otherwise one is generated. Unhandled failures return a safe JSON
error with the same request ID.

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
