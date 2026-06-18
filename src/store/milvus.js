/**
 * Milvus VectorStore — delegates to data/ and milvus/ helpers.
 * Active when DB_BACKEND=milvus (or legacy MILVUS_HOST is set).
 */

import {
  createCollection,
  dropCollection,
  upsertRows,
  entityCount,
  listArticles,
} from "../data/collection.js";

import { searchDocuments } from "../core/search.js";

export function getMilvusStore() {
  return {
    createCollection,
    dropCollection,
    upsertRows,
    entityCount,
    listArticles,
    search: searchDocuments,
    async ping() {
      const { getMilvusClient } = await import("../milvus/client.js");
      const client = getMilvusClient();
      const version = await client.ping();
      const address = client.getAddress();
      return { address, version };
    },
  };
}
