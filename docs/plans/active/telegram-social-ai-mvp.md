# Execution Plan: Telegram Social AI MVP

Date: 2026-07-29

## Status

Active

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

## Validation

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

## Result

SPEC-001 through SPEC-003 are implemented and validated. This plan remains
active for the Telegram MVP; SPEC-004 and later product behavior remain
unimplemented.
