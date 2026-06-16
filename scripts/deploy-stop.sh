#!/usr/bin/env bash
# Stop the vector-search-demo HTTP server (Commander Deploy tab: Stop).
#
# Stops the node server. When DATA_BACKEND=milvus (or STOP_MILVUS=1), also tears
# down the docker-compose Milvus stack so it stops consuming resources.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PORT="${PORT:-8011}"
DATA_BACKEND="${DATA_BACKEND:-mock}"
PID_FILE="$ROOT/.deploy-server.pid"

if [ -f "$PID_FILE" ]; then
  PID="$(cat "$PID_FILE")"
  if kill -0 "$PID" 2>/dev/null; then
    kill "$PID" 2>/dev/null || true
    sleep 0.5
    kill -9 "$PID" 2>/dev/null || true
  fi
  rm -f "$PID_FILE"
fi

PIDS="$(lsof -ti "tcp:${PORT}" 2>/dev/null || true)"
if [ -n "$PIDS" ]; then
  # shellcheck disable=SC2086
  kill $PIDS 2>/dev/null || true
fi

if [ "$DATA_BACKEND" = "milvus" ] || [ "${STOP_MILVUS:-0}" = "1" ]; then
  echo "[deploy-stop] tearing down Milvus stack (docker compose down)..."
  docker compose down 2>/dev/null || true
fi

echo "Stopped vector-search-demo on port $PORT (backend $DATA_BACKEND)."
