#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/python ] || [ ! -d frontend/dist ]; then
  echo "Run bash scripts/setup.sh first."
  exit 1
fi
if [ -z "${OLLAMA_MODEL+x}" ] && [ -f .local/ollama-model ]; then
  IFS= read -r OLLAMA_MODEL < .local/ollama-model
  export OLLAMA_MODEL
fi
exec .venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 --workers 1
