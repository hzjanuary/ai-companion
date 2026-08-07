# SPEC-023 Implementation Handoff

## Status

APPROVED CANDIDATE

SPEC-023 has a repository-safe implementation of the production observability
contract — a closed SLI catalog, SLO targets with a rolling 28-day error budget,
a content-safe alert rule catalog, and metadata-only incident operations — with
deterministic synthetic proof, the full non-Docker validation estate green, and
Docker-backed local validation under the temporary host-only override. It is
`APPROVED CANDIDATE` (not complete) because the Product-Owner-approved latency
targets are accompanied by proposed operating-owner objectives (availability,
delivery confirmation, and dead-letter/quarantine backlog and stale-lease caps)
and notification channels that still require explicit operating-owner
ratification before production reliance, and because the SPEC-022 live Telegram
acceptance blocker remains externally gated. No commit or push was performed and
no schema migration was added.

## 1. Executive Summary

SPEC-023 turns the repository's existing content-free operational evidence into
an observable, approved-candidate production commitment without changing the
runtime. Every SLI and alert input already exists: the 34-metric `january_`
catalog and loopback exporter (SPEC-015/018/019), the durable recovery
classifications and `operations inspect` CLI (SPEC-016), the bounded `/health`
and `/ready` surfaces, the content-safe control-plane audit (SPEC-021), and the
evidence and ownership vocabulary (SPEC-022). The implementation adds
declarative definitions, content-safe artifacts, runbooks, ADRs, and proof — and
no schema migration.

- `backend/app/application/observability/` (6 modules) is a pure,
  deterministic, application-layer computation surface: a closed 10-SLI catalog
  mapped to existing measurement sources; SLO objectives and error-budget
  evaluation over a rolling 28-day window (nearest-rank p95, unknown windows
  reported as unknown and never zero); an 11-rule content-safe alert catalog
  with severity caps, debounce, acknowledgement expiry, and escalation; and
  metadata-only incident evidence and post-incident-review builders. It never
  runs inside the webhook acknowledgement path, never supervises workers, and
  never mutates production.
- Alerting policy: burn-rate thresholds 14.4x (fast) / 6.0x (slow) / 1x (base),
  per-rule debounce (300 s for the SEV1 mention burn, 900 s for the other burn
  and recovery rules, 1800 s for readiness dependency, 60 s for readiness
  recovery, none for alerting staleness), ack expiry SEV1 900 s / SEV2 3600 s /
  SEV3 86400 s / SEV4 none, escalation order
  `operating_owner -> incident_contact -> rollback_authority`.
- Content safety is enforced at the application layer: every rendered alert
  payload, incident evidence bundle, and post-incident review passes
  `assert_content_safe`, which rejects the forbidden keys and
  credential-shaped strings already enforced by SPEC-022.
- Operator-facing documentation: `docs/runbooks/slos-alerting.md`,
  `docs/runbooks/alerting.md`, `docs/runbooks/incident-operations.md`, and the
  evidence templates `docs/templates/incident-evidence.md` and
  `docs/templates/post-incident-review.md`.
- ADRs 0019 (SLO and alert evaluation model) and 0020 (incident and error-budget
  state representability) record the material decisions; 0020 records the
  no-migration audit outcome.
- One validator, `scripts/validate-observability.sh`, was extended (the only
  validator added or changed) with the SPEC-023 unit tests, ruff/format/mypy, a
  no-migration guard, and a Python proof that builds synthetic verdicts
  (SEV1 mention burn, SEV2 quarantine, SEV1 readiness, SEV2 staleness), renders
  content-safe payloads, and builds evidence and review artifacts.
- The product roadmap in `docs/product/SPEC.md` and `docs/product/README.md`
  now records SPEC-023 as "implemented as an approved candidate".

Two pre-existing, out-of-scope validation defects were discovered and are
documented in Known Limitations (Section 10): a semantic-memory integration
test that fails on any non-pristine test database due to cross-run state leakage
from the rebuild test, and `validate-backup-restore.sh`, whose hard-coded Alembic
revision expectation (`0013_semantic_memory_index`) went stale when SPEC-021
added migration 0014. Both reproduce at baseline HEAD and were not introduced
or fixed by SPEC-023.

## 2. Repository Baseline

- Baseline HEAD: `527b4d2` (`feat(spec-022): implement Telegram production
  integration and live acceptance`).
- `origin/main` matches the baseline commit; nothing is committed or pushed.
- The worktree contained pre-existing SPEC-023 product-document changes
  (`M docs/product/SPEC.md`, `M docs/product/README.md`, and the new untracked
  `docs/product/specs/SPEC-023-production-observability-slos-alerting-and-incident-operations.md`)
  and the pre-existing design contract
  `docs/plans/handoff/SPEC-023-DESIGN-HANDOFF.md`.
- The implementation phase added the modules, tests, validator extension, ADRs,
  runbooks, templates, roadmap references, and this handoff. The database schema
  is unchanged; the Alembic head remains `0014_authenticated_control_plane`.

## 3. Implemented

### `backend/app/application/observability/` (6 files, 1162 lines)

- `slis.py`: the closed `SLI_CATALOG` of 10 SLIs — webhook ack latency, health/
  readiness latency, mention response latency, command response latency, ingress
  ack durability, delivery confirmation rate, recovery backlog, provider error
  rate, rate-limit pressure, and readiness-degraded time — each with an
  unambiguous definition, a validity rule, a unit, and a mapping to an existing
  measurement source (`SLI_BY_NAME`, `validate_sli_catalog`). No SLI introduces
  a new measurement source.
- `slos.py`: `WINDOW_DAYS = 28`; `LatencyObjective`,
  `GoodRatioObjective`, and `BacklogObjective`; `percentile` (nearest-rank p95),
  `evaluate_latency`, `evaluate_good_ratio`, `evaluate_backlog`, and
  `recovery_counts`. Approved latency targets: webhook ack p95 < 500 ms; health
  p95 < 250 ms; non-LLM command p95 < 1 s; mention response p95 < 8 s.
  Availability, delivery-confirmation, and backlog/stale-lease objectives are
  recorded as proposed operating-owner defaults
  (`PROPOSED_OPERATOR_OBJECTIVES`, `DEFAULT_RECOVERY_OBJECTIVE`) and are never
  claimed as approved policy. A window with missing metric or exporter data is
  reported `unknown`, never zero.
- `alerts.py`: `Severity` (SEV1..SEV4), `FAST_BURN_THRESHOLD = 14.4`,
  `SLOW_BURN_THRESHOLD = 6.0`, `STALENESS_THRESHOLD_SECONDS = 900`,
  `ACK_EXPIRY_SECONDS`, `ALERT_RULES` (11 rules), `DebounceGate`,
  `escalate_verdict`, `escalation_step`, `render_alert_payload`,
  `evaluate_alerts`, and `AlertInputs`. Rules: four burn-rate rules
  (`burn_mention_response` SEV1, `burn_webhook_ack` SEV2,
  `burn_health_readiness` SEV3, `burn_command_response` SEV3), four recovery-risk
  rules (`recovery_dead_letter_backlog` SEV2, `recovery_quarantine_accumulation`
  SEV2, `recovery_stale_leases` SEV2, `worker_backlog_oldest_pending` SEV3), and
  three readiness/staleness rules (`readiness_dependency` SEV1,
  `readiness_recovery` SEV4, `alerting_staleness` SEV2). Every rule enforces a
  severity cap (`_cap`).
- `incidents.py`: `INCIDENT_PHASES` (detection, acknowledgement, classification,
  response, communication, mitigation, resolution, review), `ROOT_CAUSE_CLASSES`
  (provider_outage, dependency_outage, capacity_exhaustion, deployment_rollout,
  configuration_error, secret_rotation, recovery_backlog, alerting_failure,
  unknown), `build_incident_evidence`, and `build_post_incident_review`.
- `content_safety.py`: `ContentSafetyViolation` and `assert_content_safe`,
  mirroring the SPEC-022 `acceptance_evidence` discipline (bot-token
  `\d{6,10}:[A-Za-z0-9_-]{35}` pattern and forbidden keys).
- `__init__.py`: the public export surface used by tests, the validator, and
  callers.

### Tests (20, deterministic, no live I/O)

- `backend/tests/test_observability_slos.py` (5 tests): catalog validity, SLI
  mapping, latency evaluation with `pytest.approx`, unknown-window handling, and
  backlog/recovery-count evaluation.
- `backend/tests/test_observability_alerts.py` (15 tests): rule catalog shape,
  severity caps, debounce gating, acknowledgement expiry and escalation,
  burn-rate classification (fast/slow/base), recovery-risk verdicts, readiness
  dependency/recovery verdicts, staleness alerting, payload rendering, and
  content-safety rejection of prohibited labels/keys.

### Validator

- `scripts/validate-observability.sh` was extended (the only validator changed):
  adds the two SPEC-023 test files to the pytest run, ruff check, ruff format
  check, and mypy strict on `backend/app/application/observability`, a
  `*023*` no-migration guard alongside the existing `*015*` guard, and a Python
  proof that validates the catalog, evaluates latency met/unknown, evaluates
  synthetic alert inputs (SEV1 mention burn, SEV2 quarantine accumulation, SEV1
  readiness dependency, SEV2 alerting staleness) through the `DebounceGate`,
  renders every payload through `render_alert_payload`, and builds
  content-safe incident evidence and post-incident review artifacts.

### Documentation

- `docs/runbooks/slos-alerting.md` (99 lines): SLI catalog, approved latency
  targets, proposed operator objectives, 28-day error-budget computation, and
  the unknown-never-zero rule.
- `docs/runbooks/alerting.md` (88 lines): the 11-rule catalog, severity model,
  burn-rate thresholds, debounce, ack expiry, escalation, and the content-safe
  notification boundary.
- `docs/runbooks/incident-operations.md` (124 lines): lifecycle, roles and
  authority (rollback authority only), communication, drills, and review.
- `docs/templates/incident-evidence.md` (47 lines) and
  `docs/templates/post-incident-review.md` (30 lines): metadata-only artifact
  templates with content-safety rules.
- `docs/decisions/0019-slo-and-alert-evaluation-model.md` (72 lines) and
  `docs/decisions/0020-incident-and-error-budget-state-representability.md` (59
  lines); `docs/decisions/README.md` indexed both.
- `docs/product/SPEC.md` and `docs/product/README.md`: roadmap updated to
  SPEC-023 "implemented as an approved candidate" pending operating-owner
  ratification of proposed objectives and notification channels.

## 4. Files Changed

| File | Change |
| --- | --- |
| `backend/app/application/observability/__init__.py` | new (104 lines) |
| `backend/app/application/observability/alerts.py` | new (487 lines) |
| `backend/app/application/observability/content_safety.py` | new (69 lines) |
| `backend/app/application/observability/incidents.py` | new (125 lines) |
| `backend/app/application/observability/slis.py` | new (132 lines) |
| `backend/app/application/observability/slos.py` | new (245 lines) |
| `backend/tests/test_observability_slos.py` | new (136 lines) |
| `backend/tests/test_observability_alerts.py` | new (302 lines) |
| `scripts/validate-observability.sh` | extended (+98 lines; the only validator touched) |
| `docs/runbooks/slos-alerting.md` | new (99 lines) |
| `docs/runbooks/alerting.md` | new (88 lines) |
| `docs/runbooks/incident-operations.md` | new (124 lines) |
| `docs/templates/incident-evidence.md` | new (47 lines) |
| `docs/templates/post-incident-review.md` | new (30 lines) |
| `docs/decisions/0019-slo-and-alert-evaluation-model.md` | new (72 lines) |
| `docs/decisions/0020-incident-and-error-budget-state-representability.md` | new (59 lines) |
| `docs/decisions/README.md` | +2 lines (index ADRs 0019/0020) |
| `docs/product/README.md` | +16/−4 lines roadmap |
| `docs/product/SPEC.md` | +15/−3 lines roadmap |
| `docs/plans/handoff/SPEC-023-HANDOFF.md` | this record |

`git diff --stat` for tracked files: 4 files changed, 117 insertions, 14
deletions. No runtime, interface, infrastructure, or migration file is changed.

## 5. ADRs

- `docs/decisions/0019-slo-and-alert-evaluation-model.md` — the SLO/error-budget
  computation and alert-evaluation model: rolling 28-day window, nearest-rank
  percentile, multi-burn-rate alerting with debounce/severity-caps/ack-expiry/
  escalation, and the unknown-never-zero rule.
- `docs/decisions/0020-incident-and-error-budget-state-representability.md` —
  the migration-audit outcome: error-budget state is computed from exported
  telemetry (no persistence); incident state is representable in existing
  content-free tables (`operational_recovery_items`/`_events`,
  `control_audit_events`); the recovery catalog exposes only
  `stale_lease_count`/`oldest_pending_age_seconds` as backlog proxies. No schema
  migration is authorized or added.

## 6. Migrations

None. SPEC-023 created and authorized no migration; no
`backend/alembic/versions/*023*` file exists and the validator enforces it. The
Alembic head remains `0014_authenticated_control_plane` (SPEC-021), confirmed by
`alembic upgrade head` in Docker validation. Existing tables plus the 34-metric
`january_` catalog represent all required state.

## 7. Validation

- `./scripts/validate-observability.sh` — PASS (exit 0): the two SPEC-023 test
  files plus the existing observability/http/planning tests, ruff check, ruff
  format check, mypy strict on the module, the no-migration guard, and the
  synthetic-proof block printing
  `Observability telemetry and SPEC-023 SLI/SLO/alert/incident artifacts: valid`.
- `./scripts/validate.sh` — PASS (exit 0): ruff, format check, mypy, harness
  checks, `git diff --check`, and the non-integration suite: **229 passed, 41
  deselected**.
- `git diff --check` — passed at the validation points.

## 8. Docker Validation

Host limitation: under the default Docker SELinux labeling profile, minimal
containers exit 139; the same commands exit 0 with `--security-opt label=disable`.
This matches the SPEC-020/021/022 findings and is a host/engine defect, not a
repository issue. DB-backed validation therefore used a temporary uncommitted
`compose.override.yaml` containing only `security_opt: ["label=disable"]` for
the project services, with isolated host ports `JANUARY_DB_HOST_PORT=5433` and
`JANUARY_REDIS_HOST_PORT=6380`. The override is removed after validation; no
committed Compose file is weakened.

- `./scripts/validate-memory.sh` — PASS on a pristine test database: 7/7
  `memory_integration` (see the state-leak limitation in Section 10).
- `./scripts/validate-reliability.sh` — 30 passed; the run stops at two
  pre-existing failures documented below (`test_memory_schema.py:324` state
  leak and `validate-backup-restore.sh` stale revision), both reproduced at
  baseline HEAD and unrelated to SPEC-023.

## 9. Runtime Proof

- Deterministic synthetic proof (in `validate-observability.sh`): the SLI
  catalog validates and every SLI maps to a catalog metric; latency evaluation
  returns `met` with a burn rate below 1 on a bounded synthetic series and
  `unknown` (not zero) on an empty window; synthetic alert inputs yield the
  expected verdicts (SEV1 mention burn, SEV2 quarantine accumulation, SEV1
  readiness dependency, SEV2 alerting staleness) through the `DebounceGate`;
  every rendered payload passes content safety; incident evidence and
  post-incident review artifacts build from metadata-only timeline entries.
- No live Telegram, provider, or external I/O is exercised; no CI or synthetic
  run claims production SLO compliance (NFR-04). SLO compliance is measured only
  in the approved environment after hosting and ownership decisions are
  accepted.

## 10. Known Limitations

- Pre-existing integration-suite state leak (SPEC-019 scope, not SPEC-023):
  `backend/tests/integration/test_memory_schema.py::test_delete_before_semantic_upsert_never_embeds_or_restores_memory`
  asserts delete targets for the base current-version collection, but
  `test_semantic_rebuild_activates_only_a_verified_fresh_collection` persists an
  active `_rebuild_` collection row in
  `explicit_memory_semantic_index_collections` for the current embedding
  version. The delete test does not reset that table, so any non-pristine test
  database (i.e., any database on which the rebuild test has ever run) fails the
  delete test. Proven at baseline HEAD `527b4d2` in isolation and in the full
  suite, and proven environmental: after deleting the leaked row the entire
  `memory_integration` suite passes 7/7. Not fixed here because it is outside
  SPEC-023 scope.
- Pre-existing stale validator (SPEC-021 scope): `scripts/validate-backup-restore.sh`
  asserts the restored database's Alembic revision is
  `0013_semantic_memory_index`, but migration `0014_authenticated_control_plane`
  was added by SPEC-021 (commit `4c01cb3`), so the validator has failed at head
  since SPEC-021. Not fixed here.
- SPEC-022 live Telegram acceptance remains externally gated (no staging bot,
  token, public HTTPS URL, or test group); live drills and production SLO
  measurement inherit that blocker.
- Proposed operating-owner objectives (availability target, delivery-confirmation
  share, dead-letter/quarantine backlog cap, maximum stale-lease age) and the
  notification channels are recorded as proposed defaults and are not approved
  policy; the validated latency targets are Product-Owner-approved.
- The recovery catalog exposes only `stale_lease_count` and
  `oldest_pending_age_seconds` as backlog proxies; there is no per-lease
  stale-age field (recorded in ADR-0020).

## 11. External Blockers

- Hosting/orchestration and monitoring/alerting/notification backends are not
  selected (SPEC-020); SLO evidence is only measured after those decisions.
- Operating-owner ratification of proposed objectives, ownership roster,
  notification channels, and acknowledgement SLA.
- SPEC-022 staging Telegram resources (approved bot, token, HTTPS URL, test
  group) for live acceptance and live drills.
- Host Docker default-profile repair (SELinux labeling or Docker/runc policy)
  before relying on default-profile validation.

## 12. Remaining Work

- Product Owner and operating-owner approval of the proposed objectives,
  severity model, ownership roster, notification channels, and ack SLA; record
  the ratified objectives as approved policy in `slos.py`/`alerts.py` and the
  runbooks.
- Content-safe drills per severity with synthetic data in a drill environment
  before production reliance.
- Production SLO/error-budget measurement and alert evaluation in the approved
  environment once telemetry export and monitoring backends exist.
- (Out of SPEC-023 scope, tracked here for awareness) clear or repair the two
  pre-existing validation defects: the memory state-leak reset and the
  `validate-backup-restore.sh` revision assertion.

## 13. Production Prerequisites

- Operating-owner ratification of the proposed objectives, ownership roster,
  notification channels, and ack SLA, and approved monitoring/alerting backend
  selection (SPEC-020).
- Metrics export enabled on the approved environment only (loopback-only port,
  `metrics_enabled`/`metrics_export_enabled`), collected behind the SPEC-020
  network boundary.
- SLO compliance measured only from approved-environment telemetry; windows
  report unknown, never zero; no CI claim of compliance.
- Alert evaluation deployed as a separate bounded surface that reads exported
  metrics and recovery state, never inside the webhook path and never as a
  worker supervisor; alerting's own staleness alertable.
- Incident records and evidence retained consistently with SPEC-011; content
  safety enforced on every artifact; rollback authority remains the only
  production-mutation role.

## 14. Exact Commands

Local deterministic validation:

```bash
./scripts/validate-observability.sh        # SPEC-023 + observability estate
./scripts/validate.sh                      # 229 passed, 41 deselected
uv run pytest backend/tests/test_observability_slos.py \
  backend/tests/test_observability_alerts.py -q    # 20 passed
```

Docker-backed validation (temporary host-only override, isolated ports):

```bash
# compose.override.yaml with only: services.*.security_opt = ["label=disable"]
JANUARY_DB_HOST_PORT=5433 JANUARY_REDIS_HOST_PORT=6380 ./scripts/validate-memory.sh
JANUARY_DB_HOST_PORT=5433 JANUARY_REDIS_HOST_PORT=6380 ./scripts/validate-reliability.sh
# then: rm -f compose.override.yaml
```

Known pre-existing DB-suite limitations (not SPEC-023): clear the leaked
semantic-index collection row before a memory run on a previously used test
database, and note `validate-backup-restore.sh` expects revision 0013 while head
is 0014.

## 15. git status --short

```
 M docs/decisions/README.md
 M docs/product/README.md
 M docs/product/SPEC.md
 M scripts/validate-observability.sh
?? backend/app/application/observability/
?? backend/tests/test_observability_alerts.py
?? backend/tests/test_observability_slos.py
?? docs/decisions/0019-slo-and-alert-evaluation-model.md
?? docs/decisions/0020-incident-and-error-budget-state-representability.md
?? docs/plans/handoff/SPEC-023-DESIGN-HANDOFF.md
?? docs/plans/handoff/SPEC-023-HANDOFF.md
?? docs/product/specs/SPEC-023-production-observability-slos-alerting-and-incident-operations.md
?? docs/runbooks/alerting.md
?? docs/runbooks/incident-operations.md
?? docs/runbooks/slos-alerting.md
?? docs/templates/incident-evidence.md
?? docs/templates/post-incident-review.md
```

`compose.override.yaml` is absent (temporary, removed after validation). HEAD and
`origin/main` are both `527b4d2`; nothing is committed or pushed.

## 16. Next Bounded Task

Obtain Product Owner and operating-owner approval of the proposed SLI/SLO
objectives, severity model, ownership roster, notification channels, and ack
SLA; then record the ratified values as approved policy, run content-safe drills
per severity in a drill environment, and begin SLO measurement and alert
evaluation in the approved environment. Separately (outside SPEC-023 scope),
repair the two pre-existing validation defects in Section 10. Do not start
SPEC-024 from this handoff.
