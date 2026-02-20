#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

if [[ ! -d ".venv" ]]; then
  echo "[error] .venv not found. run setup first."
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate

CELERY_WORKER_POOL="${CELERY_WORKER_POOL:-solo}"
CELERY_WORKER_CONCURRENCY="${CELERY_WORKER_CONCURRENCY:-1}"
ENABLE_SQLITE_FALLBACK="${ENABLE_SQLITE_FALLBACK:-1}"
HEALTH_CHECK_RETRIES="${HEALTH_CHECK_RETRIES:-30}"
HEALTH_CHECK_INTERVAL_SEC="${HEALTH_CHECK_INTERVAL_SEC:-1}"

try_start_service() {
  local svc="$1"
  if command -v service >/dev/null 2>&1; then
    service "${svc}" start >/dev/null 2>&1 || true
  fi
  if command -v sudo >/dev/null 2>&1; then
    sudo -n service "${svc}" start >/dev/null 2>&1 || true
  fi
}

ensure_redis() {
  if command -v redis-cli >/dev/null 2>&1 && redis-cli ping >/dev/null 2>&1; then
    echo "[ok] redis reachable"
    return
  fi
  echo "[info] redis not reachable, trying to start service..."
  try_start_service "redis-server"
  if command -v redis-cli >/dev/null 2>&1 && redis-cli ping >/dev/null 2>&1; then
    echo "[ok] redis reachable"
  else
    echo "[warn] redis still unreachable. worker may fail."
  fi
}

ensure_postgres() {
  if command -v pg_isready >/dev/null 2>&1 && pg_isready -h localhost -p 5432 >/dev/null 2>&1; then
    echo "[ok] postgres reachable"
    return
  fi
  echo "[info] postgres not reachable, trying to start service..."
  try_start_service "postgresql"
  if command -v pg_isready >/dev/null 2>&1 && pg_isready -h localhost -p 5432 >/dev/null 2>&1; then
    echo "[ok] postgres reachable"
  else
    echo "[warn] postgres still unreachable. API may fail at startup."
  fi
}

check_database_connection() {
  python - <<'PY'
from sqlalchemy import create_engine, text
from app.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
with engine.connect() as conn:
    conn.execute(text("SELECT 1"))
print("ok")
PY
}

ensure_postgres
ensure_redis

if ! check_database_connection >/tmp/memorialtube_db_check.log 2>&1; then
  echo "[warn] database connect check failed."
  tail -n 20 /tmp/memorialtube_db_check.log || true
  if [[ "${ENABLE_SQLITE_FALLBACK}" == "1" ]]; then
    export DATABASE_URL="sqlite:///${REPO_ROOT}/data/local.db"
    echo "[warn] DATABASE_URL switched to SQLite fallback: ${DATABASE_URL}"
  else
    echo "[error] database connection failed and SQLite fallback is disabled."
    echo "[hint] set ENABLE_SQLITE_FALLBACK=1 or fix PostgreSQL credentials/database."
    exit 1
  fi
else
  echo "[ok] database connect check passed"
fi

# avoid duplicated workers/servers if script is executed multiple times
pkill -f "uvicorn app.main:app" >/dev/null 2>&1 || true
pkill -f "celery -A app.celery_app worker" >/dev/null 2>&1 || true
sleep 1

nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 >/tmp/memorialtube_api.log 2>&1 &
API_PID=$!

nohup celery -A app.celery_app worker -l info --pool "${CELERY_WORKER_POOL}" --concurrency "${CELERY_WORKER_CONCURRENCY}" >/tmp/memorialtube_worker.log 2>&1 &
WORKER_PID=$!

echo "[ok] API PID: ${API_PID}"
echo "[ok] Worker PID: ${WORKER_PID}"
echo "[ok] Worker pool: ${CELERY_WORKER_POOL} (concurrency=${CELERY_WORKER_CONCURRENCY})"
echo "[ok] API log: /tmp/memorialtube_api.log"
echo "[ok] Worker log: /tmp/memorialtube_worker.log"

for _ in $(seq 1 "${HEALTH_CHECK_RETRIES}"); do
  if curl --max-time 2 -fsS http://127.0.0.1:8000/api/v1/health >/dev/null 2>&1; then
    echo "[ok] Health check passed: http://127.0.0.1:8000/api/v1/health"
    exit 0
  fi
  if ! kill -0 "${API_PID}" >/dev/null 2>&1; then
    echo "[error] API process exited during startup."
    break
  fi
  sleep "${HEALTH_CHECK_INTERVAL_SEC}"
done

echo "[error] Health check failed. API is not responding."
echo "[hint] tail -n 80 /tmp/memorialtube_api.log"
echo "[hint] tail -n 80 /tmp/memorialtube_worker.log"
exit 1
