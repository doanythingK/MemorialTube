#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${PROJECT_ROOT}"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR=".venv"
WITH_AI=0
SKIP_PIP_UPGRADE=0

log() {
  printf '[setup] %s\n' "$*"
}

warn() {
  printf '[setup][warn] %s\n' "$*" >&2
}

die() {
  printf '[setup][error] %s\n' "$*" >&2
  exit 1
}

usage() {
  cat <<'EOF'
Usage: ./setup.sh [options]

Options:
  --with-ai           Install optional AI dependencies (requirements-ai.txt)
  --venv-dir <path>   Virtual environment directory (default: .venv)
  --python <binary>   Python binary to use (default: python3)
  --skip-pip-upgrade  Skip "pip install --upgrade pip"
  -h, --help          Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-ai)
      WITH_AI=1
      shift
      ;;
    --venv-dir)
      [[ $# -ge 2 ]] || die "--venv-dir requires a value"
      VENV_DIR="$2"
      shift 2
      ;;
    --python)
      [[ $# -ge 2 ]] || die "--python requires a value"
      PYTHON_BIN="$2"
      shift 2
      ;;
    --skip-pip-upgrade)
      SKIP_PIP_UPGRADE=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "Unknown option: $1 (use --help)"
      ;;
  esac
done

[[ -f "requirements.txt" ]] || die "requirements.txt not found. Run this script from the repository root."

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  die "Python not found: ${PYTHON_BIN}. Install Python 3.10+ and retry."
fi

if ! "${PYTHON_BIN}" - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY
then
  die "Python version must be >= 3.10. Current: $("${PYTHON_BIN}" -V 2>&1)"
fi

if ! "${PYTHON_BIN}" -m venv --help >/dev/null 2>&1; then
  die "Python venv module is unavailable. On Debian/Ubuntu install python3-venv."
fi

if [[ ! -d "${VENV_DIR}" ]]; then
  log "Creating virtualenv at ${VENV_DIR}"
  if ! "${PYTHON_BIN}" -m venv "${VENV_DIR}"; then
    die "Failed to create virtualenv. Check permission and python3-venv package."
  fi
else
  log "Using existing virtualenv at ${VENV_DIR}"
fi

# shellcheck disable=SC1090
source "${VENV_DIR}/bin/activate"

if ! command -v pip >/dev/null 2>&1; then
  log "pip not found in virtualenv; bootstrapping with ensurepip"
  if ! "${PYTHON_BIN}" -m ensurepip --upgrade; then
    die "Failed to bootstrap pip via ensurepip."
  fi
fi

if [[ "${SKIP_PIP_UPGRADE}" -eq 0 ]]; then
  log "Upgrading pip"
  if ! pip install --upgrade pip; then
    die "pip upgrade failed. Check network/proxy or package index access."
  fi
fi

log "Installing base dependencies (requirements.txt)"
if ! pip install -r requirements.txt; then
  die "Base dependency install failed. Check network/proxy and Python build tooling."
fi

if [[ "${WITH_AI}" -eq 1 ]]; then
  [[ -f "requirements-ai.txt" ]] || die "requirements-ai.txt not found."
  log "Installing optional AI dependencies (requirements-ai.txt)"
  if ! pip install -r requirements-ai.txt; then
    die "AI dependency install failed. Check CUDA/torch compatibility and network access."
  fi
fi

if [[ ! -f ".env" && -f ".env.example" ]]; then
  cp .env.example .env
  log "Created .env from .env.example"
fi

ffmpeg_path=""
if [[ -n "${FFMPEG_PATH:-}" && "${FFMPEG_PATH}" != "ffmpeg" ]]; then
  if [[ -x "${FFMPEG_PATH}" ]]; then
    ffmpeg_path="${FFMPEG_PATH}"
  else
    warn "FFMPEG_PATH is set but not executable: ${FFMPEG_PATH}"
  fi
fi

if [[ -z "${ffmpeg_path}" ]]; then
  if command -v ffmpeg >/dev/null 2>&1; then
    ffmpeg_path="$(command -v ffmpeg)"
  fi
fi

if [[ -z "${ffmpeg_path}" ]]; then
  die "ffmpeg not found. Install ffmpeg or set FFMPEG_PATH in .env (example: ./bin/ffmpeg)."
fi

log "ffmpeg detected at ${ffmpeg_path}"
log "Setup completed successfully."
log "Activate virtualenv: source ${VENV_DIR}/bin/activate"
log "Run API: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
