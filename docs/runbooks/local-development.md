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

## Validation

Run the repository's canonical local validation command:

```bash
./scripts/validate.sh
```

It runs pytest, Ruff lint, Ruff formatting verification, mypy, Harness status
and doctor checks, and `git diff --check` when Git is available. No external
service or credential is required.

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
