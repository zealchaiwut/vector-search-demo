/**
 * Postgres VectorStore — adapts PgVectorStore to the factory interface.
 * Active when DB_BACKEND=postgres. Requires DATABASE_URL to be set.
 */

import { searchDocuments } from "../core/search.js";

async function _getImpl() {
  const { getPgStore } = await import("./PgVectorStore.js");
  return getPgStore();
}

export function getPostgresStore() {
  return {
    async createCollection() {
      const store = await _getImpl();
      await store.migrate();
    },
    async dropCollection() {
      const store = await _getImpl();
      await store._query("DROP TABLE IF EXISTS articles");
    },
    async upsertRows(rows) {
      if (!rows || rows.length === 0) return;
      const store = await _getImpl();
      await store.upsert(rows);
    },
    async entityCount() {
      const store = await _getImpl();
      return store.count();
    },
    async listArticles() {
      const store = await _getImpl();
      return store.list();
    },
    async deleteArticle(articleId) {
      const store = await _getImpl();
      return store.delete(articleId);
    },
    async listChunks() {
      const store = await _getImpl();
      return store.listChunks();
    },
    search: searchDocuments,
    async ping() {
      const store = await _getImpl();
      const ts = await store.ping();
      const url = process.env.DATABASE_URL ?? "(DATABASE_URL not set)";
      return { address: url, version: String(ts) };
    },
  };
}
