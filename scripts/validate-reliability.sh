#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UV="${UV:-uv}"
if ! command -v "$UV" >/dev/null 2>&1; then UV="$ROOT/.tools/uv"; fi
if [[ ! -x "$UV" ]]; then echo "uv is required; run the documented local setup" >&2; exit 127; fi
cd "$ROOT"
"$UV" run pytest \
  backend/tests/test_concurrency.py \
  backend/tests/test_outbound.py \
  backend/tests/test_planning_service.py \
  backend/tests/test_config.py \
  backend/tests/test_observability.py
JANUARY_DB_HOST_PORT="${JANUARY_DB_HOST_PORT:-5433}" "$ROOT/scripts/validate-db.sh"
JANUARY_DB_HOST_PORT="${JANUARY_DB_HOST_PORT:-5433}" \
  JANUARY_REDIS_HOST_PORT="${JANUARY_REDIS_HOST_PORT:-6380}" \
  "$ROOT/scripts/validate-ingress.sh"
JANUARY_DB_HOST_PORT="${JANUARY_DB_HOST_PORT:-5433}" \
  JANUARY_REDIS_HOST_PORT="${JANUARY_REDIS_HOST_PORT:-6380}" \
  "$ROOT/scripts/validate-conversation.sh"
JANUARY_DB_HOST_PORT="${JANUARY_DB_HOST_PORT:-5433}" \
  JANUARY_REDIS_HOST_PORT="${JANUARY_REDIS_HOST_PORT:-6380}" \
  "$ROOT/scripts/validate-planning.sh"
JANUARY_DB_HOST_PORT="${JANUARY_DB_HOST_PORT:-5433}" \
  JANUARY_REDIS_HOST_PORT="${JANUARY_REDIS_HOST_PORT:-6380}" \
  "$ROOT/scripts/validate-delivery.sh"
JANUARY_DB_HOST_PORT="${JANUARY_DB_HOST_PORT:-5433}" \
  JANUARY_REDIS_HOST_PORT="${JANUARY_REDIS_HOST_PORT:-6380}" \
  "$ROOT/scripts/validate-commands.sh"
JANUARY_DB_HOST_PORT="${JANUARY_DB_HOST_PORT:-5433}" \
  JANUARY_REDIS_HOST_PORT="${JANUARY_REDIS_HOST_PORT:-6380}" \
  "$ROOT/scripts/validate-memory.sh"
JANUARY_DB_HOST_PORT="${JANUARY_DB_HOST_PORT:-5433}" \
  JANUARY_REDIS_HOST_PORT="${JANUARY_REDIS_HOST_PORT:-6380}" \
  "$ROOT/scripts/validate-safety.sh"
JANUARY_REDIS_HOST_PORT="${JANUARY_REDIS_HOST_PORT:-6380}" docker compose up -d redis >/dev/null
JANUARY_REDIS_URL="redis://127.0.0.1:${JANUARY_REDIS_HOST_PORT:-6380}/0" \
  "$UV" run pytest -m safety_integration backend/tests/integration/test_redis_concurrency.py
JANUARY_REDIS_HOST_PORT="${JANUARY_REDIS_HOST_PORT:-6380}" docker compose stop redis >/dev/null
JANUARY_DB_HOST_PORT="${JANUARY_DB_HOST_PORT:-5433}" "$ROOT/scripts/validate-backup-restore.sh"
"$UV" run ruff check backend/app
echo "Reliability checks: valid"
