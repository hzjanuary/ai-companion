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

Every response includes `X-Request-ID`. A syntactically valid incoming value is
preserved; otherwise one is generated. Unhandled failures return a safe JSON
error with the same request ID.
