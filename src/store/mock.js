/**
 * Mock VectorStore — file-backed (collection.json).
 * Delegates to the data/ helpers that use the file path when DB_BACKEND=mock.
 */

import {
  createCollection,
  dropCollection,
  upsertRows,
  entityCount,
  listArticles,
  deleteArticle,
  listChunks,
} from "../data/collection.js";

import { searchDocuments } from "../core/search.js";

export function getMockStore() {
  return {
    createCollection,
    dropCollection,
    upsertRows,
    entityCount,
    listArticles,
    deleteArticle,
    listChunks,
    search: searchDocuments,
    async ping() {
      return { address: "file-backed (mock)", version: "n/a" };
    },
  };
}
