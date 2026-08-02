#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$project_root/scripts/lib/resolve-uv.sh"
uv_bin="$(resolve_uv "$project_root")"

export JANUARY_DB_HOST_PORT="${JANUARY_DB_HOST_PORT:-5433}"
export JANUARY_REDIS_HOST_PORT="${JANUARY_REDIS_HOST_PORT:-6380}"
export JANUARY_QDRANT_HOST_PORT="${JANUARY_QDRANT_HOST_PORT:-6333}"
export JANUARY_DATABASE_PORT="$JANUARY_DB_HOST_PORT"
export JANUARY_REDIS_URL="redis://127.0.0.1:${JANUARY_REDIS_HOST_PORT}/0"
export JANUARY_QDRANT_URL="http://127.0.0.1:${JANUARY_QDRANT_HOST_PORT}"

docker compose up -d database redis qdrant

trap 'docker compose stop database redis qdrant >/dev/null' EXIT

for _ in $(seq 1 30); do
  if docker compose exec -T database pg_isready -U january -d january >/dev/null 2>&1 \
    && docker compose exec -T redis redis-cli ping >/dev/null 2>&1 \
    && curl -fsS "$JANUARY_QDRANT_URL/healthz" >/dev/null; then
    break
  fi
  sleep 1
done
docker compose exec -T database pg_isready -U january -d january >/dev/null
docker compose exec -T redis redis-cli ping >/dev/null
curl -fsS "$JANUARY_QDRANT_URL/healthz" >/dev/null
"$uv_bin" run alembic upgrade head
"$uv_bin" run pytest \
  backend/tests/test_semantic_memory.py \
  backend/tests/test_config.py \
  backend/tests/test_conversation_context.py -q
"$uv_bin" run pytest backend/tests/integration/test_memory_schema.py -m memory_integration -q
"$uv_bin" run alembic downgrade 0012_conversation_summaries
"$uv_bin" run alembic upgrade head
