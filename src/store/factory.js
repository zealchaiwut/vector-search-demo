/**
 * VectorStore factory.
 *
 * Reads DB_BACKEND (or DATA_BACKEND for legacy compatibility) to determine
 * which VectorStore implementation the CLI commands should use.
 *
 * Supported values:
 *   mock     – file-backed collection.json (default; no external services)
 *   milvus   – live Milvus instance (requires MILVUS_HOST or docker compose)
 *   postgres – Postgres-backed store (requires PG connection; not yet wired)
 *
 * Commands call resolveBackend() then logActiveBackend() at startup, then
 * getStore(backend) to get a VectorStore implementation.
 */

const SUPPORTED_BACKENDS = ["milvus", "postgres", "mock"];

/**
 * Read and validate DB_BACKEND. Falls back to DATA_BACKEND for legacy callers.
 * Throws with the unrecognised value when the env var is set to something unknown.
 */
export function resolveBackend() {
  const raw = (process.env.DB_BACKEND || process.env.DATA_BACKEND || "")
    .trim()
    .toLowerCase();
  const backend = raw || "mock";
  if (!SUPPORTED_BACKENDS.includes(backend)) {
    throw new Error(
      `[backend] unrecognised DB_BACKEND: "${raw}" (supported: ${SUPPORTED_BACKENDS.join(", ")})`
    );
  }
  return backend;
}

/** Emit the standard startup log line to stdout. */
export function logActiveBackend(backend) {
  process.stdout.write(`[backend] active store: ${backend}\n`);
}

/**
 * Return a VectorStore object for the given backend name.
 * All returned stores share the same async interface:
 *   createCollection(), dropCollection(), upsertRows(rows),
 *   entityCount(), listArticles(),
 *   search(query, k), ping()
 */
export async function getStore(backend) {
  switch (backend) {
    case "milvus": {
      const { getMilvusStore } = await import("./milvus.js");
      return getMilvusStore();
    }
    case "postgres": {
      const { getPostgresStore } = await import("./postgres.js");
      return getPostgresStore();
    }
    case "mock":
    default: {
      const { getMockStore } = await import("./mock.js");
      return getMockStore();
    }
  }
}
