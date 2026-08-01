#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$project_root/scripts/lib/resolve-uv.sh"
uv_bin="$(resolve_uv "$project_root")"

"$uv_bin" run pytest backend/tests/test_observability.py backend/tests/test_http.py \
  backend/tests/test_planning_service.py -q
"$uv_bin" run python - "$project_root" <<'PY'
from pathlib import Path
import sys

root = Path(sys.argv[1])
text = (root / "backend/app/infrastructure/telemetry.py").read_text()
required = {
    "january_http_requests_total", "january_http_request_duration_seconds",
    "january_telegram_updates_total", "january_conversation_eligibility_total",
    "january_planning_jobs_total", "january_model_requests_total",
    "january_model_request_duration_seconds", "january_model_tokens_total",
    "january_model_usage_reports_total", "january_response_plan_validation_total",
    "january_outbound_actions_total", "january_telegram_send_failures_total",
    "january_delivery_duration_seconds", "january_safety_decisions_total",
    "january_rate_limit_events_total", "january_worker_operations_total",
}
missing = sorted(name for name in required if name not in text)
if missing:
    raise SystemExit(f"missing telemetry metric definitions: {', '.join(missing)}")
if any(root.glob("backend/alembic/versions/*015*")):
    raise SystemExit("SPEC-015 must not add a migration")
print("Observability telemetry artifacts: valid")
PY
