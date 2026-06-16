#!/usr/bin/env bash
# Start the vector-search-demo HTTP server (Commander Deploy tab: Start).
#
# Backend selection via DATA_BACKEND (default: mock):
#   DATA_BACKEND=mock   → file-backed collection.json, no Milvus. Auto-seeds
#                         demo data (runs `ingest`) when the collection is empty,
#                         so the UI shows results without standing up Milvus.
#   DATA_BACKEND=milvus → brings up the docker-compose Milvus stack, waits for
#                         it to accept connections, then serves against it.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PORT="${PORT:-8011}"
DATA_BACKEND="${DATA_BACKEND:-mock}"
PID_FILE="$ROOT/.deploy-server.pid"
LOG_FILE="$ROOT/deploy-server.log"
COLLECTION_FILE="$ROOT/collection.json"

export PORT DATA_BACKEND

# Already running? Leave it be.
if [ -f "$PID_FILE" ]; then
  OLD_PID="$(cat "$PID_FILE")"
  if kill -0 "$OLD_PID" 2>/dev/null; then
    echo "Server already running (PID $OLD_PID, port $PORT, backend $DATA_BACKEND)."
    exit 0
  fi
  rm -f "$PID_FILE"
fi

echo "[deploy-start] backend=$DATA_BACKEND port=$PORT"

if [ "$DATA_BACKEND" = "milvus" ]; then
  echo "[deploy-start] starting Milvus stack (docker compose up -d)..."
  docker compose up -d
  HOST="${MILVUS_HOST:-localhost}"
  MPORT="${MILVUS_PORT:-19530}"
  echo "[deploy-start] waiting for Milvus at ${HOST}:${MPORT}..."
  for i in $(seq 1 60); do
    if nc -z "$HOST" "$MPORT" 2>/dev/null; then
      echo "[deploy-start] Milvus is up."
      break
    fi
    if [ "$i" = "60" ]; then
      echo "ERROR: Milvus did not become ready in time" >&2
      exit 1
    fi
    sleep 2
  done
  # Ensure the app talks to the local stack.
  export MILVUS_HOST="$HOST"
  export MILVUS_PORT="$MPORT"
else
  # Mock: seed demo data when the collection is empty or missing.
  if [ ! -s "$COLLECTION_FILE" ] || [ "$(cat "$COLLECTION_FILE" 2>/dev/null)" = "[]" ]; then
    echo "[deploy-start] mock collection empty — seeding demo data (ingest)..."
    if ! DATA_BACKEND=mock node src/cli.js ingest >> "$LOG_FILE" 2>&1; then
      echo "WARN: ingest failed; starting with an empty collection (see $LOG_FILE)" >&2
    fi
  fi
fi

# Prefer .env when present (extra config like EMBEDDING_MODEL); our exported
# PORT/DATA_BACKEND/MILVUS_* still win — Node's --env-file does not override
# variables already set in the environment.
if [ -f "$ROOT/.env" ]; then
  nohup node --env-file="$ROOT/.env" src/server.mjs >> "$LOG_FILE" 2>&1 &
else
  nohup node src/server.mjs >> "$LOG_FILE" 2>&1 &
fi
PID=$!
echo "$PID" > "$PID_FILE"
echo "Started vector-search-demo (PID $PID, port $PORT, backend $DATA_BACKEND). Logs: $LOG_FILE"
