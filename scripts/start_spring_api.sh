#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SPRING_ROOT="${REPO_ROOT}/spring-api"

if [[ ! -d "${SPRING_ROOT}" ]]; then
  echo "[error] spring-api directory not found."
  exit 1
fi

if ! command -v gradle >/dev/null 2>&1; then
  echo "[error] gradle not found. Install Gradle 8+ first."
  exit 1
fi

if ! command -v java >/dev/null 2>&1; then
  echo "[error] java not found. Install JDK 21+ first."
  exit 1
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "[error] ffmpeg not found. Install FFmpeg first."
  exit 1
fi

cd "${SPRING_ROOT}"
exec gradle bootRun
