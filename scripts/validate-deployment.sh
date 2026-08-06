#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$root/scripts/lib/resolve-uv.sh"
uv_bin="$(resolve_uv "$root")"
export COMPOSE_PROJECT_NAME="january-spec020"
export JANUARY_BACKEND_IMAGE="january-backend:spec-020-validation"
export JANUARY_DATABASE_NAME="january_staging"
export JANUARY_DATABASE_USER="january_staging"
export JANUARY_DATABASE_PASSWORD="synthetic-staging-password"
export JANUARY_TELEGRAM_BOT_TOKEN="synthetic-bot-token"
export JANUARY_TELEGRAM_PLATFORM_CONNECTION_ID="00000000-0000-0000-0000-000000000020"
export JANUARY_TELEGRAM_WEBHOOK_SECRET_TOKEN="synthetic-webhook-secret"
export JANUARY_TELEGRAM_WEBHOOK_PUBLIC_BASE_URL="https://staging.example.invalid"
export JANUARY_LLM_OPENAI_MODEL="synthetic-model"
export JANUARY_LLM_OPENAI_API_KEY="synthetic-provider-key"

cleanup() {
  docker compose -f "$root/compose.staging.yaml" down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker compose -f "$root/compose.staging.yaml" config >/dev/null
env -u JANUARY_LLM_ENABLED -u JANUARY_TELEGRAM_ENABLED \
  -u JANUARY_OUTBOUND_DELIVERY_ENABLED -u JANUARY_COMMAND_WORKER_ENABLED \
  -u JANUARY_LLM_PRIMARY_PROVIDER -u JANUARY_LLM_OPENAI_MODEL \
  -u JANUARY_LLM_OPENAI_API_KEY \
  "$uv_bin" run pytest backend/tests/test_lifecycle.py backend/tests/test_config.py -q
"$uv_bin" run python - "$root" <<'PY'
from pathlib import Path
import sys

root = Path(sys.argv[1])
text = (root / "compose.staging.yaml").read_text()
for forbidden in ("january-local", "password: january", ".env.production"):
    if forbidden in text:
        raise SystemExit(f"forbidden staging default: {forbidden}")
required = (
    "migration", "backend", "dispatcher", "conversation", "planning",
    "commands", "outbound", "retention", "stop_grace_period",
    "service_completed_successfully",
)
missing = [item for item in required if item not in text]
if missing:
    raise SystemExit(f"missing deployment artifact entries: {', '.join(missing)}")
dockerfile = (root / "Dockerfile").read_text()
if "USER january" not in dockerfile:
    raise SystemExit("runtime image must run as the non-root january user")
if "COPY --from=builder --chown=january:january" not in dockerfile:
    raise SystemExit("runtime image files must be owned by the non-root runtime user")
print("Deployment artifact checks: valid")
PY
echo "Deployment validation: valid (configuration and lifecycle proof; no external I/O)"
