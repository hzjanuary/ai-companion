# Local Development

## Prerequisites

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- Docker and Docker Compose for container workflows

Install `uv` so it is available on your normal shell `PATH`; no system-wide
Python package installation is required. The validation script prefers that
command and falls back to an executable at `.tools/uv` when one is present.
When neither is available, it stops with an installation message before running
any checks.

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
the application and database component states.

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

The Compose scope intentionally contains only the backend. Readiness reflects
only this application in SPEC-001.
