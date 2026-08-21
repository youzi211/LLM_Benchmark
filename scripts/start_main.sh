#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST_ADDRESS="${HOST_ADDRESS:-0.0.0.0}"
PORT="${PORT:-8020}"

cd "$ROOT"
cmd=(uv run)
if [[ "${NO_SYNC:-0}" == "1" ]]; then
  cmd+=(--no-sync)
fi
cmd+=(uvicorn app.main:app --host "$HOST_ADDRESS" --port "$PORT")
exec "${cmd[@]}"
