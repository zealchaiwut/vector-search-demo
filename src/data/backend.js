/**
 * Data-backend selector.
 *
 * Decides whether the app talks to a live Milvus instance or the file-backed
 * mock collection (collection.json).
 *
 * Explicit control via DATA_BACKEND:
 *   DATA_BACKEND=milvus  → use Milvus
 *   DATA_BACKEND=mock    → use the file-backed mock (no Milvus needed)
 *
 * Mock is the default so the UI runs without standing up the Milvus docker
 * stack. For backward compatibility, when DATA_BACKEND is unset the presence
 * of MILVUS_HOST selects Milvus (older behavior).
 */

export function useMilvus() {
  const backend = (process.env.DATA_BACKEND || "").trim().toLowerCase();
  if (backend === "milvus") return true;
  if (backend === "mock") return false;
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
