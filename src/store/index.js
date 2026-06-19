/**
 * VectorStore factory — reads DB_BACKEND and returns the appropriate store instance.
 *
 * DB_BACKEND=milvus   (or unset) → MilvusStore
 * DB_BACKEND=mock                → MockStore (in-memory, for unit tests)
 * DB_BACKEND=postgres            → PostgresStore (stub — methods throw "not implemented")
 * anything else                  → throws a descriptive error immediately
 */

import { MilvusStore } from "./milvus-store.js";
import { MockStore } from "./MockStore.js";
import { PostgresStore } from "./postgres-store.js";

function getMilvusAddress() {
  const host = process.env.MILVUS_HOST || "localhost";
  const port = process.env.MILVUS_PORT || "19530";
  if (process.env.MILVUS_HOST || process.env.MILVUS_PORT) {
    return `${host}:${port}`;
  }
  return process.env.MILVUS_ADDRESS || `${host}:${port}`;
}

export function createStore() {
  const backend = (process.env.DB_BACKEND || "milvus").trim().toLowerCase();
  switch (backend) {
    case "milvus":
      return new MilvusStore(getMilvusAddress());
    case "mock":
      return new MockStore();
    case "postgres":
      return new PostgresStore();
    default:
      throw new Error(
        `Unknown DB_BACKEND: "${process.env.DB_BACKEND}". Accepted values: milvus, postgres, mock.`
      );
  }
}

let _store = null;

export function getStore() {
  if (!_store) {
    _store = createStore();
  }
  return _store;
}

export function _resetStoreForTesting() {
  _store = null;
}
