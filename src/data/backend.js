/**
 * Data-backend selector.
 *
 * Decides whether the app talks to a live Milvus instance or the file-backed
 * mock collection (collection.json).
 *
 * DB_BACKEND takes priority; DATA_BACKEND is the legacy alias. When neither is
 * set, the presence of MILVUS_HOST selects Milvus (backward compatibility).
 *
 *   DB_BACKEND=milvus  → use Milvus
 *   DB_BACKEND=mock    → use the file-backed mock (no Milvus needed)
 *   DB_BACKEND=postgres → postgres (not yet wired; factory handles the error)
 */

export function useMilvus() {
  // DB_BACKEND wins; fall back to DATA_BACKEND for legacy callers.
  const backend = (process.env.DB_BACKEND || process.env.DATA_BACKEND || "")
    .trim()
    .toLowerCase();
  if (backend === "milvus") return true;
  if (backend === "mock" || backend === "postgres") return false;
  // No explicit backend chosen — infer from MILVUS_HOST (legacy behavior).
  return Boolean(process.env.MILVUS_HOST);
}

/**
 * gRPC address for the Milvus client. MILVUS_HOST/MILVUS_PORT win; when
 * DATA_BACKEND=milvus is set without a host, default to localhost:19530
 * (the docker-compose standalone instance).
 */
export function milvusAddress() {
  const host = process.env.MILVUS_HOST || "localhost";
  const port = process.env.MILVUS_PORT || "19530";
  return `${host}:${port}`;
}
