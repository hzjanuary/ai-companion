# SPEC-021 Implementation Handoff

## Status

PARTIALLY COMPLETE

SPEC-021 has a repository-safe first implementation of the authenticated control-plane boundary. It remains PARTIALLY COMPLETE because the host's default Docker SELinux labeling profile still terminates containers with code 139 and external identity-provider, staging, and operator acceptance prerequisites remain unperformed. Docker validation was completed with a temporary host-only label override; that override is not a repository or production configuration.

## Implementation phases

1. Identity boundary

   Added provider-neutral signed bearer-token validation for the control-plane routes. Tokens must carry issuer, subject, audience, expiry, and a valid HS256 signature configured through an external secret. Identities are keyed by `(issuer, subject)` and disabled identities fail closed.

2. Durable control-plane state

   Added additive PostgreSQL tables for tenants, operator identities, memberships, assistant and connection bindings, group bindings, immutable group configuration revisions, content-safe audit events, and idempotency records. Migration `0014_authenticated_control_plane` follows the existing Alembic chain and does not create schema at application startup.

3. Authorization and API boundary

   Added `/control/v1` routes for session introspection/logout, operator profile, tenant bootstrap/listing, member listing/addition/removal, assistant CRUD/disable/status, connection CRUD/disable/rotate/status, group reads, compare-and-swap group configuration updates, revision listing/restoration, and audit reads. Membership and role checks are tenant-scoped and deny by default.

4. Runtime integration boundary

   Control-plane routes are only mounted when explicitly enabled. Existing Telegram routes, command authorization, workers, ingress, delivery, retention, memory, summaries, safety, rate limiting, and observability paths were not redesigned. Control-plane mutations use short database transactions and do not perform external Telegram calls while holding a transaction.

5. Validation and handoff

   Static checks, type checks, offline migration rendering, legacy unit tests, Compose configuration rendering, repository hygiene checks, and a staging-shaped Docker run were completed. The default host security profile remains an external validation defect.

## Docker failure investigation

The original code-139 result was reproduced twice with the repository Compose file. On both runs, unrelated services failed identically:

- `postgres:16-alpine` exited `139`.
- `redis:7-alpine` exited `139`.
- Docker inspection reported `OOMKilled=false`, an empty `.State.Error`, and no application/container log output before exit.
- The failure occurred before PostgreSQL initialization or Redis startup logging, so no SPEC-021 migration or application code was executing.

The failure is not image-specific or repository-specific. Independent checks produced the same result:

- `docker run --name spec021-hello hello-world` exited `139` with empty output.
- `docker run --name spec021-alpine alpine:3.20 /bin/true` exited `139` with `OOMKilled=false` and empty `.State.Error`.
- `--security-opt seccomp=unconfined` did not change the Alpine result.
- `--security-opt label=disable` made the same Alpine command exit `0`.
- `--privileged` also made it exit `0`.

Docker reports Linux `x86_64`, `openSUSE Tumbleweed`, Docker Engine `29.4.0-ce`, runc `1.4.3`, cgroup v2, and SELinux enabled. `dmesg` was inaccessible to the current user and `journalctl -k` had no visible entries, so there is no kernel stack trace available. The controlled label-only experiment is sufficient to attribute the default-profile crash to host SELinux labeling/runtime integration, not SPEC-021.

The committed Compose files were not weakened. A temporary uncommitted override containing only `security_opt: ["label=disable"]` was used for local proof and removed after validation. The host/engine owner should repair SELinux labeling or Docker/runc policy before relying on the default profile.

During the staging-shaped rerun, a separate pre-existing repository configuration issue was found: `compose.staging.yaml` did not provide `JANUARY_REDIS_URL` to the migration service, while staging Settings reject loopback Redis defaults. The migration therefore failed with a Pydantic validation error before connecting to PostgreSQL. The required non-feature fix adds `JANUARY_REDIS_URL: redis://redis:6379/0` to that service. It is unrelated to code 139.

## Architectural boundaries

- PostgreSQL remains the source of truth for tenant relationships, operator memberships, resource bindings, revisions, audit metadata, and idempotency state.
- Control-plane resources reference existing assistants and platform connections through tenant bindings; the implementation does not add a second Telegram runtime or worker supervisor.
- The control plane does not grant Telegram group-admin authority. Existing Telegram command authorization remains responsible for Telegram-side permissions.
- Authentication is externalized to signed claims and an injected secret. No local password table, Telegram identity trust, client-supplied role, or client-supplied tenant relationship is accepted.
- Control-plane responses and audit records contain identifiers and configuration metadata only. Conversation content, tokens, cookies, authorization headers, and credential values are not returned or logged by the new routes.
- Configuration writes use an expected revision and create a new immutable revision. A stale expected revision returns a conflict and does not overwrite the current state.
- No database lock or transaction is held across Telegram, identity-provider, or other external I/O. Secret rotation is represented as a pending audited operation; the external secret-manager operation is not performed by this change.

## Migration strategy

Migration `0014_authenticated_control_plane` is additive and depends on `0013_semantic_memory_index`.

- Expand: create control-plane tables and indexes without changing existing runtime tables or backfilling conversation content.
- Validate: apply the migration in a disposable PostgreSQL environment, verify foreign keys, uniqueness constraints, JSONB columns, revision monotonicity, and the Alembic head.
- Contract: no contract/drop step is included in this migration. Existing SPEC-001 through SPEC-020 schema remains intact.
- Rollback: disable `JANUARY_CONTROL_PLANE_ENABLED`, stop exposing `/control/v1`, and retain the additive tables for forward-fix or an explicitly reviewed downgrade. Do not downgrade a production database without an operator-approved backup and rehearsal.
- Application startup does not run migrations. Deployment must run the reviewed Alembic migration as a separate step.

## API changes

When `JANUARY_CONTROL_PLANE_ENABLED=true`, the following versioned surface is mounted:

- Session/profile: `GET /control/v1/session`, `POST /control/v1/session/logout`, `GET /control/v1/me`.
- Tenants/members: `GET/POST /control/v1/tenants`, member list/add/remove under `/tenants/{tenant_id}/members`.
- Assistants: list/create/update/disable/status under `/tenants/{tenant_id}/assistants`.
- Connections: list/create/update/disable/rotate/status under `/tenants/{tenant_id}/connections`.
- Groups/revisions: group list/get/update, revision list, and restore under `/tenants/{tenant_id}/groups`.
- Audit: `GET /control/v1/tenants/{tenant_id}/audit-events`.

The first authenticated identity may create the first tenant and becomes its owner. Subsequent membership changes require an owner or admin; the last owner cannot be removed. Responses use stable control-plane error categories through the existing request-ID boundary. Credential references are treated as metadata and credential values are never returned.

The current implementation intentionally does not add a dashboard, direct-DB CLI, provider-specific OAuth callback flow, external secret-manager adapter, or automatic Telegram webhook mutation.

## Runtime changes

- Control-plane configuration is disabled by default and requires issuer, audience, and a secret of at least 32 characters when enabled.
- Every request validates issuer, audience, expiry, required claims, signature, and disabled identity state.
- The control plane upserts only the authenticated identity key; access still requires an explicit tenant membership.
- Group configuration changes are local durable revisions. No new worker is started and no external platform call is made inside the request transaction.
- Existing `/`, `/health`, `/live`, `/ready`, Telegram webhook, and worker behavior is preserved apart from readiness recognizing migration head `0014_authenticated_control_plane`.

## Worker impact

No worker implementation changed. Existing workers continue to use their existing queues, leases, idempotency, recovery, and authorization boundaries. A future bounded task is required to connect control-plane group revisions to runtime configuration consumption and to implement durable asynchronous secret rotation; those operations must recheck tenant authorization and revocation at execution time.

## Validation plan and evidence

Implemented and locally validated:

- `git diff --check` — passed at the validation points.
- `.venv/bin/ruff check backend/app alembic/versions/0014_authenticated_control_plane.py` — passed.
- `.venv/bin/mypy` — passed: no issues in 105 source files.
- `.venv/bin/pytest -q` — passed: 189 passed, 41 deselected.
- `PYTHONPATH=backend .venv/bin/alembic upgrade head --sql` — passed; rendered the complete chain through `0014_authenticated_control_plane`.
- `docker compose -f compose.yaml config` — passed.
- `docker compose -f compose.staging.yaml config` with synthetic required values — passed after the migration Redis wiring fix.
- Python compile/import checks for application and migration — passed.

Docker validated:

- With the temporary host-only SELinux label override: `database` and `redis` became healthy; the locally built SPEC-021 image built successfully; the staging-shaped migration exited `0`; backend, dispatcher, conversation, planning, commands, outbound, and retention services stayed up; and `/`, `/health`, `/live`, `/ready`, and `/docs` returned HTTP `200`.
- Readiness recovery was exercised: stopping database returned `/ready` HTTP `503`, restarting it returned HTTP `200`, and dispatcher restart completed successfully.
- The default host profile remains unvalidated for application startup because the independent minimal-container test still exits `139` without the label override.
- All temporary validation containers, networks, volumes, and the temporary override file were removed. Only older pre-existing `lumi-ai-spec018-baseline-*` stopped containers remain.

Externally blocked:

- Disposable PostgreSQL downgrade/upgrade and live control-plane API flow with control-plane authentication enabled.
- Full Docker-backed legacy integration matrix.
- OIDC/OAuth provider configuration, key rotation, revocation, MFA/step-up, secret-manager integration, staging deployment, TLS, backup/restore, and operator acceptance.

## Acceptance checklist

- [x] Control-plane routes are explicitly enabled and versioned.
- [x] Authentication fails closed and validates issuer, audience, expiry, required claims, and signature.
- [x] Identity keys use `(issuer, subject)` and disabled identities are rejected.
- [x] Tenant memberships and role gates are server-side and deny by default.
- [x] Cross-tenant resource access is filtered by tenant binding.
- [x] The last tenant owner cannot be removed.
- [x] Assistant and connection mutations do not return credential values.
- [x] Group writes use immutable revisions and expected-version conflict detection.
- [x] Audit events are content-safe and request-correlated.
- [x] Additive migration and offline Alembic rendering are present.
- [x] Existing local unit/regression validators pass.
- [ ] Provider-specific external identity integration and production key management.
- [ ] Durable idempotency replay behavior wired into every high-impact mutation.
- [ ] Async rotation/recovery worker with authorization recheck and durable operation status.
- [ ] Runtime consumption of control-plane group revisions.
- [ ] Docker-backed migration, Compose, and full integration validation.
- [ ] Dashboard/CLI acceptance through the API-only boundary.
- [ ] Staging deployment, backup/restore rehearsal, TLS, monitoring, and operator sign-off.

## Recovery guidance

1. If control-plane behavior is unsafe, set `JANUARY_CONTROL_PLANE_ENABLED=false` and redeploy. Existing Telegram runtime routes remain the operational path.
2. Preserve the database and audit records; do not delete control-plane tables during incident response.
3. Inspect request IDs and content-safe audit events for the affected tenant. Do not request or copy bearer tokens, cookies, or credential values into logs.
4. For a stale write, reload the current group revision and retry with that explicit expected revision. Never force an overwrite by bypassing the API.
5. For a suspected membership compromise, disable the identity record, revoke the upstream session/token, and verify owner membership before restoring access.
6. Restore from backup or apply a reviewed forward-fix if migration validation reveals a schema fault. Perform any downgrade only in a disposable database first and verify the Alembic head.
7. Before re-enabling the control plane, complete provider key/revocation tests, Docker-backed migration validation, staging smoke tests, backup/restore rehearsal, and operator approval.
8. If Docker again exits with code 139, first run a minimal `alpine:3.20 /bin/true` container. If it fails while `--security-opt label=disable` succeeds, repair host SELinux labeling/runtime policy; do not add that override to committed production Compose files.

## Exact repository state

- Baseline HEAD at start: `7c2fc4e52cc27dadc677edaf2c62d24afd5c9ba6`.
- `origin/main` at start: `7c2fc4e52cc27dadc677edaf2c62d24afd5c9ba6`.
- No commit or push was performed.
- Expected SPEC-021 worktree changes are the control-plane settings, models, HTTP boundary, migration, dependency metadata, the required staging migration Redis environment wiring, and this handoff.
- Recommended next bounded task: repair or replace the local Docker database/Redis environment, then run the disposable migration/API/integration acceptance flow before choosing production approval.
