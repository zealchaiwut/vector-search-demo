#!/usr/bin/env bash
# Stop the vector-search-demo HTTP server (Commander Deploy tab: Stop).
#
# Stops the node server. When DATA_BACKEND=milvus (or STOP_MILVUS=1), also tears
# down the docker-compose Milvus stack so it stops consuming resources.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PORT="${PORT:-8011}"
# Resolve backend the same way deploy-start.sh does: explicit env, else .env,
# else mock. Only milvus needs teardown; postgres/mock leave their services up.
env_val() {
  [ -f "$ROOT/.env" ] && grep -E "^$1=" "$ROOT/.env" | tail -1 | cut -d= -f2- || true
}
DB_BACKEND="${DB_BACKEND:-$(env_val DB_BACKEND)}"
DATA_BACKEND="${DATA_BACKEND:-$(env_val DATA_BACKEND)}"
BACKEND="$(echo "${DB_BACKEND:-${DATA_BACKEND:-mock}}" | tr '[:upper:]' '[:lower:]')"
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

if [ "$BACKEND" = "milvus" ] || [ "${STOP_MILVUS:-0}" = "1" ]; then
  echo "[deploy-stop] tearing down Milvus stack (docker compose down)..."
  docker compose down 2>/dev/null || true
fi

echo "Stopped vector-search-demo on port $PORT (backend $BACKEND)."
