# Local Development

## Prerequisites

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- Docker and Docker Compose for PostgreSQL/Redis container workflows

Install `uv` so it is available on your normal shell `PATH`; no system-wide
Python package installation is required. The validation script prefers that
command and falls back to an executable at `.tools/uv` when one is present.
When neither is available, it stops with an installation message before running
any checks.

Telegram remains disabled unless `JANUARY_TELEGRAM_ENABLED=true` and a token is
provided. The normal validation suite uses mock transport only. An operator may
run `./scripts/verify-telegram.sh` to explicitly perform a `getMe` identity
check; it is not part of CI or canonical validation.

Update delivery is also disabled by default. Configure exactly one mode only:
`webhook` needs a platform connection UUID, HTTPS public base URL, and secret;
`polling` needs a platform connection UUID. Neither starts inside the API
process.

## Setup And Run

```bash
uv sync --all-groups
cp .env.example .env
uv run uvicorn app.main:app --app-dir backend --reload
```

The service listens on `http://127.0.0.1:8000`. Available endpoints are `/`,
`/health`, `/live`, `/ready`, and `/docs`. `.env` is local-only; it must not
contain or commit production secrets.

## Database And Migrations

Start PostgreSQL and apply the schema before expecting readiness to succeed:

```bash
docker compose up -d database
uv run alembic upgrade head
```

Validate the database lifecycle and PostgreSQL integration tests with:

```bash
./scripts/validate-db.sh
```

It starts the project-owned database, upgrades, runs integration tests,
downgrades to base, re-upgrades, and stops that database service without
removing its volume. `/live` never checks PostgreSQL; `/ready` returns a safe
`503` when the database or required schema is unavailable; `/health` reports
the application, database, and Redis component states. Redis is `disabled`
until update delivery is enabled.

## Telegram Ingress

Run PostgreSQL and Redis ingress proof with isolated host ports:

```bash
JANUARY_DB_HOST_PORT=5433 JANUARY_REDIS_HOST_PORT=6380 ./scripts/validate-ingress.sh
```

It starts only `database` and `redis`, migrates, runs webhook, polling, outbox,
and Stream integration tests, then stops those services. No real Telegram API
call occurs.

Configured operators use explicit commands only:

```bash
./scripts/telegram-webhook.sh inspect
./scripts/telegram-webhook.sh register
./scripts/telegram-webhook.sh remove
uv run python -m app.runtime.telegram_poller
uv run python -m app.runtime.ingress_outbox_dispatcher
```

`remove --drop-pending-updates` is required to request pending-update removal.
The poller refuses to run when Telegram reports an existing webhook.

## Conversation Processing

The conversation consumer is separate from the API, poller, and outbox
dispatcher. It reads Redis references and requires PostgreSQL and Redis:

```bash
uv run python -m app.runtime.conversation_worker
```

Run its isolated integration proof with:

```bash
JANUARY_DB_HOST_PORT=5433 JANUARY_REDIS_HOST_PORT=6380 ./scripts/validate-conversation.sh
```

It uses synthetic durable Telegram updates only. No Telegram credential,
network request, LLM, or outgoing message is involved.

## Response Planning

LLM planning is disabled by default and is a separate runtime. Set a provider,
model, and required remote credential only in local operator configuration;
Ollama is the keyless local option. Do not add provider credentials to source
control.

```bash
uv run python -m app.runtime.response_planning_worker
JANUARY_DB_HOST_PORT=5433 JANUARY_REDIS_HOST_PORT=6380 ./scripts/validate-planning.sh
```

The validation command uses a fake provider and synthetic context. It checks
the `0004_response_planning` schema, leases, durable attempt/plan handoff, and
duplicate worker execution without a public provider or Telegram request.

For an explicitly configured operator, `./scripts/verify-model-provider.sh`
checks configuration without network access. `--live` requires both LLM flags
and sends one small synthetic structured request; it prints only provider,
model, and local validation success.

## Outbound Delivery

Outbound delivery is disabled by default and runs only in its own process:

```bash
uv run python -m app.runtime.outbound_delivery_worker
JANUARY_DB_HOST_PORT=5433 JANUARY_REDIS_HOST_PORT=6380 ./scripts/validate-delivery.sh
```

The delivery validator migrates to `0005_outbound_delivery` and uses synthetic
no-network tests. Timeout, transport, and malformed post-send outcomes become
terminal `delivery_unknown`; they are never retried automatically.

List uncertain actions without message content, or intentionally requeue one
only after accepting a possible duplicate:

```bash
uv run python -m app.runtime.outbound_recovery
uv run python -m app.runtime.outbound_recovery ACTION_UUID --confirm-possible-duplicate
```

## Telegram Commands

Deterministic Telegram administration commands run in a separate worker and
are disabled unless `JANUARY_COMMAND_WORKER_ENABLED=true`:

```bash
uv run python -m app.runtime.telegram_command_worker
JANUARY_DB_HOST_PORT=5433 JANUARY_REDIS_HOST_PORT=6380 ./scripts/validate-commands.sh
```

The validator uses project PostgreSQL/Redis plus fake boundaries only. See
[`telegram-administration-commands.md`](telegram-administration-commands.md)
for guarded live acceptance steps.

## Validation

Run the repository's canonical local validation command:

```bash
./scripts/validate.sh
```

It runs pytest, Ruff lint, Ruff formatting verification, mypy, Harness status
and doctor checks, and `git diff --check` when Git is available. No external
service or credential is required.

For SPEC-009 PostgreSQL/Redis personality, snapshot, policy, and fake-adapter
proofs, run:

```bash
JANUARY_DB_HOST_PORT=5433 JANUARY_REDIS_HOST_PORT=6380 \
  ./scripts/validate-personality.sh
```

For SPEC-011 explicit-memory, privacy, and retention schema proof, run:

```bash
JANUARY_DB_HOST_PORT=5433 JANUARY_REDIS_HOST_PORT=6380 \
  ./scripts/validate-memory.sh
```

It uses only project PostgreSQL/Redis and synthetic values, upgrades through
`0008_memory_privacy_retention`, tests the schema, downgrades to
`0007_telegram_commands`, then re-upgrades. To run one bounded raw-content
retention pass outside validation, enable the dedicated no-network worker:

```bash
JANUARY_RETENTION_WORKER_ENABLED=true uv run python -m app.runtime.retention_worker --once
```

## Guarded Telegram Demo

The optional polling-only dedicated-bot workflow is documented in
[`telegram-end-to-end-demo.md`](telegram-end-to-end-demo.md). It is disabled by
default and uses the ignored `.env.demo` file created by
`./scripts/january-demo.sh init`. The script requires explicit confirmation for
live Telegram/provider checks and runs API, poller, dispatcher, conversation,
planning, command, and outbound workers as separate local processes. Its synthetic
validator uses only project PostgreSQL/Redis and fake adapters:

```bash
JANUARY_DB_HOST_PORT=5433 JANUARY_REDIS_HOST_PORT=6380 ./scripts/validate-demo.sh
```

## Container Run

```bash
docker compose up --build backend
```

When port `8000` is already occupied, select another host port without changing
the container port:

```bash
JANUARY_HOST_PORT=8002 docker compose up --build backend
```

Stop it with:

```bash
docker compose down
```

The Compose scope contains the backend, PostgreSQL, and Redis 7. Telegram
remains disabled unless explicitly configured. When delivery is enabled,
readiness requires both PostgreSQL and Redis but never calls Telegram.
