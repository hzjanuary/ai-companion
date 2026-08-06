# SPEC-020 Implementation Handoff

Status: APPROVED CANDIDATE

Repository implementation: COMPLETE

Deployment acceptance: PENDING EXTERNAL PRODUCTION PREREQUISITES

## Baseline

- Repository: `/home/hzjanuary/Documents/lumi-ai`
- Baseline commit: `4736edb5f583530a8eeac3e4b967475614c53e7b`
- `origin/main` at inspection: `fab18171d2b5b34728018b00cefb0add1c7d274c`
- No commit or push was performed.
- Existing SPEC-020 design changes were present at task start and were retained.

## Implemented scope

SPEC-020 adds target-neutral production deployment and runtime operations material:

- `compose.staging.yaml` defines a separate API, migration, and worker topology with fail-closed required environment variables, health checks, restart policy, and graceful-stop periods.
- `backend/app/runtime/lifecycle.py` provides signal-aware draining and bounded waits for long-running workers.
- All nine long-running worker entry points now use the shared lifecycle signal handling.
- Production-like configuration rejects debug logging, local default database credentials, and loopback database hosts in staging/production.
- Production-like configuration also rejects loopback Redis coordination endpoints.
- `safe_configuration_fingerprint()` exposes only non-secret operational metadata.
- `scripts/validate-deployment.sh` validates Compose interpolation, deployment artifact structure, lifecycle tests, and forbidden secret/default patterns.
- ADR 0018, architecture notes, deployment notes, and the production operations runbook document topology, secrets, lifecycle, migrations, rollback, recovery, and webhook operations.
- No migration was added or changed; the existing migration chain remains the single-owner deployment step.

All repository implementation tasks defined by SPEC-020 are complete. The
remaining items below are deployment acceptance decisions and infrastructure
prerequisites, not missing repository implementation.

## Files added or modified

Added:

- `backend/app/runtime/lifecycle.py`
- `backend/tests/test_lifecycle.py`
- `compose.staging.yaml`
- `docs/decisions/0018-production-runtime-operations.md`
- `docs/plans/handoff/SPEC-020-DESIGN-HANDOFF.md`
- `docs/product/specs/SPEC-020-production-deployment-secrets-and-runtime-operations.md`
- `docs/runbooks/production-operations.md`
- `scripts/validate-deployment.sh`
- `docs/plans/handoff/SPEC-020-HANDOFF.md`

Modified:

- `.github/workflows/ci.yml`
- `backend/app/core/config.py`
- `backend/app/runtime/conversation_summary_worker.py`
- `backend/app/runtime/conversation_worker.py`
- `backend/app/runtime/ingress_outbox_dispatcher.py`
- `backend/app/runtime/outbound_delivery_worker.py`
- `backend/app/runtime/response_planning_worker.py`
- `backend/app/runtime/retention_worker.py`
- `backend/app/runtime/semantic_memory_index_worker.py`
- `backend/app/runtime/telegram_command_worker.py`
- `backend/app/runtime/telegram_poller.py`
- `docs/ARCHITECTURE.md`
- `docs/decisions/README.md`
- `docs/product/README.md`
- `docs/product/SPEC.md`
- `docs/runbooks/deployment.md`

## Architecture and deployment decisions

- The API remains stateless and does not run migrations or hidden workers.
- The migration service runs `alembic upgrade head` once before application roles.
- API readiness is intended to cover required database, Redis, and schema dependencies; liveness is process-only.
- Qdrant, Ollama, and optional semantic/summary providers remain independently degradable when configured fallbacks are safe.
- PostgreSQL is canonical; Redis is coordination; Qdrant is rebuildable derived state.
- Secrets are supplied externally and are never committed. Rotation uses controlled restart by default.
- Ambiguous Telegram sends remain quarantined as `delivery_unknown`; deployment retries do not invent delivery certainty.
- The Compose file is a staging-shaped reference artifact, not a cloud-provider or orchestrator selection.

## Validation evidence

Passed:

- `./scripts/validate.sh`
  - 189 tests passed, 41 deselected
  - formatting check passed for 143 files
  - Ruff passed for backend
  - mypy passed for 104 source files
  - Harness checks passed
- `./scripts/validate-deployment.sh`
  - 35 focused lifecycle/config tests passed
  - deployment artifact checks passed
  - fail-closed Compose interpolation validation passed with synthetic values
- `.github/workflows/ci.yml` now invokes `./scripts/validate-deployment.sh`.
- `./scripts/validate-observability.sh`
  - 20 observability tests passed
  - telemetry artifact checks passed
- `bash -n scripts/validate-deployment.sh`
- `git diff --check`
- `docker build --tag january-backend:spec-020 .`
- Docker daemon access was verified with `id`, Docker socket inspection, `docker info`, and `docker ps`.

The complete existing validation matrix also passed:

- `./scripts/validate-reliability.sh` — reliability, migration, ingress,
  conversation, planning, delivery, command, memory, safety, Redis
  concurrency, backup/restore, and Ruff checks.
- `./scripts/validate-scalability.sh` — 3 integration scenarios passed with
  zero duplicate terminal effects.
- `./scripts/validate-ambient.sh` — 60 unit tests and 31 integration tests
  passed.
- `./scripts/validate-summaries.sh` — 17 focused tests, 31 integration tests,
  Ruff, and mypy passed.
- `./scripts/validate-semantic-memory.sh` — 46 focused tests and 7 integration
  tests passed, including migration downgrade/upgrade.
- `./scripts/validate-zalo-feasibility.sh` and
  `./scripts/validate-zalo-verification.sh` — artifact checks passed; no Zalo
  runtime was introduced.

## Docker/runtime evidence and limitation

The staging-shaped stack was first attempted with the default host security
profile. PostgreSQL, Redis, and Qdrant exited with code 139, and an independent
BusyBox container reproduced the failure. Docker reported an x86_64 server and
the inspected images were `linux/amd64`; a BusyBox run with
`--security-opt label=disable` succeeded, identifying the host SELinux labeling
configuration as the local runtime issue.

The committed deployment artifact was not weakened. A temporary, uncommitted
Compose override disabled SELinux labeling only for local validation. With
synthetic, non-secret values and the locally built image, the staging-shaped
stack then provided the following evidence:

- migration container exit code `0`
- `/`, `/health`, `/live`, `/ready`, and `/docs`: HTTP `200`
- database stopped: `/ready` HTTP `503`
- database restarted: `/ready` HTTP `200`
- Qdrant stopped: `/ready` HTTP `200` (optional dependency semantics)
- dispatcher stopped and restarted successfully
- backend stopped and restarted successfully, returning `/ready` HTTP `200`

The stack was cleaned with `docker compose down -v --remove-orphans`; no
persistent test volumes or containers remain. Graceful stop/restart was proven
for worker and API containers, while real staging ingress and external webhook
acceptance remain separate prerequisites.

## Security and privacy

Synthetic credentials were used only for local validation and were not written to repository files. Logs and configuration fingerprints are designed to avoid secrets and message content. Existing privacy, safety, Telegram delivery, retention, and consent behavior was preserved.

## Deployment acceptance items

These items require deployment-owner/Product Owner decisions or external
production infrastructure. They are not implementation gaps in this
repository:

- approved production hosting/orchestration target and operating owner;
- external secret manager, key-management boundary, and rotation authority;
- production TLS ingress and domain;
- Telegram webhook registration and cutover approval;
- production monitoring, alerting, image-scanning, and audit destinations;
- PostgreSQL backup destination and approved restore rehearsal;
- rollback image/configuration destination and change-approval owner;
- production credentials, dedicated staging resources, and operator sign-off.

The local Docker daemon required a temporary SELinux-labeling override for
runtime proof. The committed deployment artifacts were not weakened, and the
override was removed. This is a host validation note, not a production
implementation limitation.

## Exact repository state

The working tree contains the SPEC-020 implementation and documentation changes listed above, with no unrelated changes introduced by this task. The tree is intentionally uncommitted for review.

## Next task

SPEC-021 is the next bounded task after Product Owner review. Do not begin it
as part of SPEC-020.

## Recovery instructions for a future Codex session

1. Read `AGENTS.md`, this handoff, the SPEC-020 product specification, and the
   current active plan.
2. Treat the current HEAD and worktree as the implementation baseline; retain
   expected SPEC-020 changes and stop only for unrelated modifications.
3. Verify `git status --short`, `git diff --check`, `git rev-parse HEAD`, and
   `git rev-parse origin/main` before changing files.
4. Run `./scripts/validate.sh`, `./scripts/validate-deployment.sh`, and the
   complete matrix recorded above.
5. If Docker exits with code 139 on this host, diagnose SELinux labeling once;
   a temporary uncommitted Compose override using `label=disable` was used for
   local proof and must not be committed or added to deployment artifacts.
6. Never use production credentials, perform public Telegram/provider side
   effects, commit, push, or start SPEC-021 during SPEC-020 recovery.
