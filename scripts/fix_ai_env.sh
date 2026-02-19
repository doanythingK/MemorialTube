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

echo "[info] Reinstalling AI dependency set (diffusers/transformers/accelerate)..."
pip install --upgrade --force-reinstall \
  "diffusers>=0.27,<1.0" \
  "transformers>=4.39,<5.0" \
  "accelerate>=0.27,<1.0" \
  "safetensors>=0.4,<1.0" \
  "sentencepiece>=0.2,<1.0"

echo "[info] Verifying imports..."
python - <<'PY'
from importlib import metadata

from diffusers import StableDiffusionInpaintPipeline
from transformers import MT5Tokenizer

print("imports=ok")
for name in ("torch", "diffusers", "transformers", "accelerate"):
    print(f"{name}={metadata.version(name)}")
PY

echo "[ok] AI dependency repair completed."
