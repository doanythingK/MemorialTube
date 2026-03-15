#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

POLL_INTERVAL_SECONDS="${POLL_INTERVAL_SECONDS:-2}"
if ! [[ "${POLL_INTERVAL_SECONDS}" =~ ^[0-9]+$ ]] || (( POLL_INTERVAL_SECONDS < 1 )); then
  POLL_INTERVAL_SECONDS=2
fi

SMOKE_TIMEOUT_SECONDS="${SMOKE_TIMEOUT_SECONDS:-}"
if [[ -z "${SMOKE_TIMEOUT_SECONDS}" ]]; then
  if [[ "${INSTALL_AI:-0}" == "1" ]]; then
    SMOKE_TIMEOUT_SECONDS=1800
  else
    SMOKE_TIMEOUT_SECONDS=240
  fi
fi
if ! [[ "${SMOKE_TIMEOUT_SECONDS}" =~ ^[0-9]+$ ]] || (( SMOKE_TIMEOUT_SECONDS < 1 )); then
  SMOKE_TIMEOUT_SECONDS=240
fi
MAX_POLLS=$(( (SMOKE_TIMEOUT_SECONDS + POLL_INTERVAL_SECONDS - 1) / POLL_INTERVAL_SECONDS ))

echo "[smoke] config: install_ai=${INSTALL_AI:-0}, timeout=${SMOKE_TIMEOUT_SECONDS}s, interval=${POLL_INTERVAL_SECONDS}s"

echo "[smoke] waiting for docker compose..."
for i in $(seq 1 60); do
  if docker compose version >/dev/null 2>&1; then
    break
  fi
  sleep "${POLL_INTERVAL_SECONDS}"
done

if ! docker compose version >/dev/null 2>&1; then
  echo "[smoke][error] docker compose is unavailable in this WSL distro."
  exit 1
fi

echo "[smoke] starting stack"
make up

echo "[smoke] waiting for API health"
HEALTH=""
for i in $(seq 1 30); do
  HEALTH="$(curl -sS http://localhost:8000/api/v1/health || true)"
  if [[ "${HEALTH}" == *"\"status\":\"ok\""* ]]; then
    break
  fi
  sleep "${POLL_INTERVAL_SECONDS}"
done

if [[ "${HEALTH}" != *"\"status\":\"ok\""* ]]; then
  echo "[smoke][error] API health check failed."
  exit 1
fi

mkdir -p data/input data/work/p1 data/output

for f in pet1.jpg pet2.jpg pet3.jpg; do
  if [[ ! -f "data/input/${f}" ]]; then
    echo "[smoke][error] missing input image: data/input/${f}"
    exit 1
  fi
done

echo "[smoke] enqueue pipeline job"
JOB_ID="$(
  curl -sS -X POST http://localhost:8000/api/v1/jobs/pipeline \
    -H "Content-Type: application/json" \
    -d '{"image_paths":["data/input/pet1.jpg","data/input/pet2.jpg","data/input/pet3.jpg"],"working_dir":"data/work/p1","final_output_path":"data/output/final_pipeline.mp4","transition_duration_seconds":6,"transition_prompt":"gentle memorial cinematic transition, soft light","transition_negative_prompt":"extra animal, distorted pet","last_clip_duration_seconds":4,"last_clip_motion_style":"zoom_in","bgm_volume":0.15}' \
    | sed -n 's/.*"job_id":"\([^"]*\)".*/\1/p'
)"

if [[ -z "${JOB_ID}" ]]; then
  echo "[smoke][error] failed to parse job_id from pipeline enqueue response."
  exit 1
fi

echo "[smoke] JOB_ID=${JOB_ID}"

FINAL_STATUS=""
LAST_RESPONSE=""
LAST_STATUS=""
LAST_STAGE=""
LAST_PROGRESS=""

for i in $(seq 1 "${MAX_POLLS}"); do
  R="$(curl -sS "http://localhost:8000/api/v1/jobs/${JOB_ID}" || true)"
  [[ -n "${R}" ]] && LAST_RESPONSE="${R}"

  STATUS="$(printf '%s' "${R}" | sed -n 's/.*"status":"\([^"]*\)".*/\1/p')"
  STAGE="$(printf '%s' "${R}" | sed -n 's/.*"stage":"\([^"]*\)".*/\1/p')"
  PROGRESS="$(printf '%s' "${R}" | sed -n 's/.*"progress_percent":\([0-9]\+\).*/\1/p')"
  elapsed="$((i * POLL_INTERVAL_SECONDS))"

  if [[ "${STATUS}" != "${LAST_STATUS}" || "${STAGE}" != "${LAST_STAGE}" || "${PROGRESS}" != "${LAST_PROGRESS}" || $((i % 10)) -eq 0 ]]; then
    echo "[smoke] t=${elapsed}s status=${STATUS:-unknown} stage=${STAGE:-unknown} progress=${PROGRESS:-?}%"
    LAST_STATUS="${STATUS}"
    LAST_STAGE="${STAGE}"
    LAST_PROGRESS="${PROGRESS}"
  fi

  if [[ "${STATUS}" == "succeeded" ]]; then
    FINAL_STATUS="succeeded"
    break
  fi
  if [[ "${STATUS}" == "failed" ]]; then
    FINAL_STATUS="failed"
    break
  fi
  sleep "${POLL_INTERVAL_SECONDS}"
done

if [[ "${FINAL_STATUS}" != "succeeded" ]]; then
  if [[ -z "${FINAL_STATUS}" ]]; then
    FINAL_STATUS="timeout"
  fi
  echo "[smoke][error] pipeline did not succeed (status=${FINAL_STATUS})."
  if [[ -n "${LAST_RESPONSE}" ]]; then
    echo "[smoke][error] last response: ${LAST_RESPONSE}"
  fi
  exit 1
fi

if [[ ! -f "data/output/final_pipeline.mp4" ]]; then
  echo "[smoke][error] output file not found: data/output/final_pipeline.mp4"
  exit 1
fi

ls -lh data/output/final_pipeline.mp4
echo "[smoke] done"
