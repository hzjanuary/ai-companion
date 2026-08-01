#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$project_root/scripts/lib/resolve-uv.sh"
uv_bin="$(resolve_uv "$project_root")"

if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  printf '%s\n' "Docker Compose is required for PostgreSQL integration validation." >&2
  exit 1
fi

export JANUARY_DATABASE_HOST=127.0.0.1
export JANUARY_DATABASE_PORT="${JANUARY_DB_HOST_PORT:-5432}"
export JANUARY_DATABASE_NAME="${JANUARY_DATABASE_NAME:-january}"
export JANUARY_DATABASE_USER="${JANUARY_DATABASE_USER:-january}"
export JANUARY_DATABASE_PASSWORD="${JANUARY_DATABASE_PASSWORD:-january-local}"

cleanup() {
  docker compose stop database >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker compose up --detach database
for _ in $(seq 1 30); do
  if docker compose exec -T database pg_isready -U "$JANUARY_DATABASE_USER" -d "$JANUARY_DATABASE_NAME" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
if ! docker compose exec -T database pg_isready -U "$JANUARY_DATABASE_USER" -d "$JANUARY_DATABASE_NAME" >/dev/null; then
  printf '%s\n' "PostgreSQL did not become ready." >&2
  exit 1
fi

"$uv_bin" run alembic upgrade head
"$uv_bin" run pytest -m "integration and not ingress_integration and not safety_integration"
"$uv_bin" run alembic downgrade base
"$uv_bin" run alembic upgrade head
