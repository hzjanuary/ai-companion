# SPEC-024 Implementation Handoff

## Status

APPROVED CANDIDATE

This is the System Architect's implementation handoff for SPEC-024 (Safety
Moderation, Abuse Prevention, and User Protection). The product specification
(`docs/product/specs/SPEC-024-safety-moderation-abuse-prevention-and-user-protection.md`)
is `APPROVED DESIGN`; this phase implements it as an approved candidate
awaiting Product Owner and operating-owner approval of the threshold
objectives and live observation. The full unit suite, the observability
validator, and the safety/command/delivery integration suites pass; the
database-backed validators below have been exercised in this worktree.

## Repository Baseline

- Baseline HEAD: `2d661c9fe042d3d1b1be4b48ad5e07578b50be23` (SPEC-023
  implemented and committed).
- The worktree contains this phase's changes plus the pre-existing Product
  Owner SPEC-024 changes (`docs/product/SPEC.md`, `docs/product/README.md`,
  and the untracked product spec). No commit or push is authorized.
- Migration head is `0015_safety_moderation`; the readiness check
  (`backend/app/infrastructure/database/database.py`) and the safety, command,
  and memory schema-pin tests reference it. The migration id is shortened from
  the descriptive name because alembic's `version_num` column is
  `varchar(32)`.

## Outcome

SPEC-024 is enforced in the runtime workers, exposed to group administrators
and the operating owner through content-free surfaces, and backed by durable
additive state and `safety_risk` alerting. Every safety gate outcome is a
content-free `safety_policy_decisions` record; protection and review state are
durable; no rejected content is stored; no member is sanctioned or profiled.

## What Was Implemented

### FR-01 / FR-06 — Observable safety pipeline and content-free signals
- `backend/app/domain/safety.py` defines the deterministic vocabulary
  (`SafetySignalType`, `SafetyReasonCode`, `SafetyDecision`,
  `SafetyStage`, `SafetyOutcome`, `ProtectionAction`, `ProtectionState`,
  `SafetyLevel`, `ReviewAction`, `ReviewItemStatus`) and pure policy helpers
  (`evaluate_protection`, `thresholds_from_settings`,
  `signal_counts_view`, `render_review_item_view`, `protection_notice`).
- `backend/app/application/safety.py` provides the
  `SafetyModerationService` (fail-closed on repository errors), threshold
  derivation per safety level, protective-action ladder
  (`stop_targeting` -> `reduce_interaction` -> `pause_interaction`), and
  `ReviewItemRecord` projection. `evaluate_and_enforce` is idempotent: a
  sustained-signal window records protection once, reversed only through
  review.
- `backend/app/infrastructure/database/safety_protection.py` is the
  fail-closed `SqlAlchemySafetyModerationRepository` over
  `safety_review_items`, `participants.protected_at`, and
  `safety_policy_decisions`.

### FR-02 / FR-04 / FR-05 — Assistant output and manipulation resistance
- `response_planning_worker.py` runs `evaluate_and_enforce` before generation
  (PAUSE completes the job with no plan; REDUCE completes with a short
  language-aware acknowledgement) and records POST_GENERATION decisions
  (`ALLOW`/`REFUSE`, `MODEL_REFUSAL`, transformed flag). Rate-limit and
  eligibility branches remain ahead of provider I/O; no configuration enables
  `answer_every_message`.

### FR-03 / FR-08 / FR-10 — Targeting protection and standing stop
- Delivery recheck `_safety_recheck` in `outbound_delivery_worker.py` runs
  before Telegram I/O for teasing plans: opted-out, privacy-deleted, missing,
  or disallowed targets return `TEASING_TARGET_OPTED_OUT`; a protected target
  returns `TARGET_PROTECTED`; the per-group teasing cap returns
  `TEASING_CAP_EXCEEDED`. Skips finalize with `stale_safety_boundary` and a
  `PRE_DELIVERY`/`SILENT` decision record. Protected members are never
  targeted; no punitive state exists.

### FR-09 — Administrator controls
- `/safety` reads status or applies `set_safety_level`
  (`strict`/`standard`/`relaxed`) and `set_teasing_cap` (`teasing 1..9`);
  `/protect` and `/unprotect` are zero-argument `CONFIGURATION` operations
  that toggle `participants.protected_at` for the replied-to member.
  `ConfigurationChange` and the immutable revision apply path carry
  `safety_level` and `teasing_cap`.

### FR-11 / FR-12 — Escalation and content-safe audit
- `telemetry.py` adds `january_safety_protective_actions_total{action}` next
  to `january_safety_decisions_total`. `alerts.py` adds the 4-rule
  `safety_risk` catalog (`safety_fail_closed_surge`, Sev2;
  `safety_protective_actions_surge`, Sev2;
  `safety_review_queue_growth`, Sev3;
  `safety_escalation_high_severity`, Sev1) and `SafetyAlertObjective`;
  `docs/runbooks/alerting.md` documents them.
- Control-plane endpoints (deny-by-default): safety aggregates, review-item
  listing (content-free), review-item actions (`safety.review.action` audit),
  and protection set/restore (`safety.protection.set` audit).

## Database Impact

Additive migration `0015_safety_moderation` (ADR
`docs/decisions/0021-safety-moderation-protection-state-and-review-queue.md`):
`participants.protected_at`,
`conversation_configuration_revisions.safety_level`/`.teasing_cap`, and the
content-free `safety_review_items` table. Downgrade to
`0008_memory_privacy_retention` then re-upgrade is exercised by
`validate-safety.sh`. Both additions are additive; downgrade drops the
protection flag and review queue without content restoration.

## Validation Run

- `pytest -q` (unit): **257 passed, 52 deselected**.
- Integration (real Postgres + Redis): safety, command, delivery, demo, and
  persistence markers **32 passed**; new `test_safety_recheck.py` **11
  passed** covering non-teasing skip, opted-out/privacy-deleted/disallowed/
  missing/protected targets, safety-off, below-cap, at-cap, no-revision, and
  the end-to-end `PRE_DELIVERY`/`SILENT` skip with `stale_safety_boundary`.
- `ruff check`, `ruff format --check`, and `mypy backend/app/` all clean
  (`Success: no issues found in 115 source files`).
- `scripts/validate-observability.sh` green (42 passed, telemetry catalog and
  SPEC-023 artifacts valid).
- New unit coverage: `test_safety.py` (8 pure-policy), `test_safety_moderation.py`
  (9 service tests over a deterministic in-memory repository),
  `test_observability_alerts.py` (safety-risk verdicts + content-safe payloads),
  extended `test_telegram_commands.py` grammar cases (58 passed).

## Remaining / Open Items

- DB-backed validators all green (exit 0) against the local compose stack
  (temporary SELinux label-disabled override): `validate-safety.sh`
  (downgrade/re-upgrade to `0015_safety_moderation`),
  `validate-commands.sh` (14 passed), `validate-memory.sh`, `validate-ingress.sh`
  (8 passed), `validate-reliability.sh`. `scripts/validate.sh` end-to-end
  passes (pytest 257, ruff, ruff-format, mypy, harness doctor, `git diff
  --check`). A clean CI/operating-environment run remains a follow-up.
- Product Owner and operating-owner approval of the `SafetyAlertObjective`
  thresholds, the `/safety` level/cap defaults, and review retention policy
  (see ADR 0021 follow-up).
- Live observation after production integration (SPEC-022 gate unchanged).

## Rollback

- Safe rollout order: deploy migration `0015_safety_moderation`, then the
  workers/commands/control-plane. Rollback: downgrade the migration, then
  revert the application code; enforcement is fail-closed so a partial rollout
  skips (never sends) rather than weakening a boundary.
- `validate-safety.sh` proves the downgrade path to `0008_memory_privacy_retention`
  and re-upgrade.
