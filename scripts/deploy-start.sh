#!/usr/bin/env bash
# Start the vector-search-demo HTTP server (Commander Deploy tab: Start).
#
# Backend selection via DB_BACKEND (legacy alias: DATA_BACKEND; default: mock).
# The value may come from the environment OR from the repo .env — Commander's
# Deploy tab only exports PORT, so the backend is read from .env here too.
#   mock     → file-backed collection.json, no external services. Auto-seeds
#              demo data (runs `ingest`) when the collection is empty.
#   milvus   → brings up the docker-compose Milvus stack, waits for it, serves.
#   postgres → uses Postgres/pgvector at DATABASE_URL (default
#              postgresql://localhost:5432/vectordb). Migrates the schema and
#              seeds demo data when the articles table is empty.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Read a single KEY=value from .env (last wins); empty when absent.
env_val() {
  [ -f "$ROOT/.env" ] && grep -E "^$1=" "$ROOT/.env" | tail -1 | cut -d= -f2- || true
}

PORT="${PORT:-8011}"
# Backend: explicit env wins, else .env, else mock. DB_BACKEND is the canonical
# selector (usePostgres() only reads DB_BACKEND); DATA_BACKEND is the legacy alias.
DB_BACKEND="${DB_BACKEND:-$(env_val DB_BACKEND)}"
DATA_BACKEND="${DATA_BACKEND:-$(env_val DATA_BACKEND)}"
BACKEND="$(echo "${DB_BACKEND:-${DATA_BACKEND:-mock}}" | tr '[:upper:]' '[:lower:]')"
PID_FILE="$ROOT/.deploy-server.pid"
LOG_FILE="$ROOT/deploy-server.log"
COLLECTION_FILE="$ROOT/collection.json"

export PORT

# Already running? Leave it be.
if [ -f "$PID_FILE" ]; then
  OLD_PID="$(cat "$PID_FILE")"
  if kill -0 "$OLD_PID" 2>/dev/null; then
    echo "Server already running (PID $OLD_PID, port $PORT, backend $BACKEND)."
    exit 0
  fi
  rm -f "$PID_FILE"
fi

echo "[deploy-start] backend=$BACKEND port=$PORT"

if [ "$BACKEND" = "postgres" ]; then
  DATABASE_URL="${DATABASE_URL:-$(env_val DATABASE_URL)}"
  # Default to local peer auth as the invoking OS user (libpq needs a username).
  DATABASE_URL="${DATABASE_URL:-postgresql://${PGUSER:-${USER:-postgres}}@localhost:5432/vectordb}"
  export DB_BACKEND=postgres DATABASE_URL
  echo "[deploy-start] postgres at ${DATABASE_URL}"
  # Migrate schema (idempotent — CREATE TABLE/EXTENSION IF NOT EXISTS).
  if ! node src/cli.js init >> "$LOG_FILE" 2>&1; then
    echo "ERROR: postgres migration failed (see $LOG_FILE)" >&2
    exit 1
  fi
  # Seed demo data only when the table is empty (ingest is destructive).
  COUNT="$(node -e 'import("./src/data/collection.js").then(m=>m.entityCount()).then(n=>process.stdout.write(String(n))).catch(()=>process.stdout.write("err"))' 2>/dev/null)"
  if [ "$COUNT" = "0" ] || [ "$COUNT" = "err" ]; then
    echo "[deploy-start] postgres empty — seeding demo data (ingest)..."
    if ! node src/cli.js ingest >> "$LOG_FILE" 2>&1; then
      echo "WARN: ingest failed; starting with an empty collection (see $LOG_FILE)" >&2
    fi
  fi
elif [ "$BACKEND" = "milvus" ]; then
  export DB_BACKEND=milvus
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
  export DB_BACKEND=mock
  # Mock: seed demo data when the collection is empty or missing.
  if [ ! -s "$COLLECTION_FILE" ] || [ "$(cat "$COLLECTION_FILE" 2>/dev/null)" = "[]" ]; then
    echo "[deploy-start] mock collection empty — seeding demo data (ingest)..."
    if ! DB_BACKEND=mock node src/cli.js ingest >> "$LOG_FILE" 2>&1; then
      echo "WARN: ingest failed; starting with an empty collection (see $LOG_FILE)" >&2
    fi
  fi
fi

# Prefer .env when present (extra config like EMBEDDING_MODEL); our exported
# PORT/DB_BACKEND/DATABASE_URL/MILVUS_* still win — Node's --env-file does not
# override variables already set in the environment.
if [ -f "$ROOT/.env" ]; then
  nohup node --env-file="$ROOT/.env" src/server.mjs >> "$LOG_FILE" 2>&1 &
else
  nohup node src/server.mjs >> "$LOG_FILE" 2>&1 &
fi
PID=$!
echo "$PID" > "$PID_FILE"
echo "Started vector-search-demo (PID $PID, port $PORT, backend $BACKEND). Logs: $LOG_FILE"
