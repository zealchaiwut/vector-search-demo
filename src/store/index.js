/**
 * Store factory.
 *
 * getStore() returns the appropriate VectorStore implementation based on the
 * DB_BACKEND environment variable:
 *
 *   DB_BACKEND=mock  → MockStore (in-memory, no external services required)
 *
 * When DB_BACKEND is unset or set to an unrecognised value, getStore() returns
 * null so callers can fall back to the legacy DATA_BACKEND / collection.json
 * path.
 */

import { MockStore } from "./MockStore.js";

let _mockInstance = null;

/**
 * Returns a VectorStore instance for the configured DB_BACKEND, or null if
 * DB_BACKEND is not set to a known value.
 *
 * @returns {Promise<MockStore|null>}
 */
export async function getStore() {
  const backend = (process.env.DB_BACKEND ?? "").trim().toLowerCase();
  if (backend === "mock") {
    if (!_mockInstance) _mockInstance = new MockStore();
    return _mockInstance;
  }
  return null;
}

export { MockStore };
