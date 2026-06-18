/**
 * Postgres VectorStore — adapts PgVectorStore to the factory interface.
 * Active when DB_BACKEND=postgres. Requires DATABASE_URL to be set.
 */

import { searchDocuments } from "../core/search.js";

async function _getImpl() {
  const { getPgStore } = await import("./PgVectorStore.js");
  return getPgStore();
}

function avgEmbeddings(embeddings) {
  if (embeddings.length === 0) return [];
  const dim = embeddings[0].length;
  const avg = new Array(dim).fill(0);
  for (const v of embeddings) {
    for (let i = 0; i < dim; i++) avg[i] += v[i];
  }
  for (let i = 0; i < dim; i++) avg[i] /= embeddings.length;
  return avg;
}

function collapseToArticles(rows) {
  const byArticle = new Map();
  for (const row of rows) {
    const articleId = row.id.split(":")[0];
    if (!byArticle.has(articleId)) {
      byArticle.set(articleId, {
        id: articleId,
        headline: row.headline,
        attachment_url: row.attachment_url,
        detailParts: [],
        embeddings: [],
      });
    }
    const entry = byArticle.get(articleId);
    entry.detailParts.push(row.details);
    if (Array.isArray(row.embedding)) entry.embeddings.push(row.embedding);
  }
  return [...byArticle.values()].map((entry) => ({
    id: entry.id,
    headline: entry.headline,
    details: entry.detailParts.join(" "),
    attachment_url: entry.attachment_url,
    embedding: avgEmbeddings(entry.embeddings),
  }));
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
      await store.upsert(collapseToArticles(rows));
    },
    async entityCount() {
      const store = await _getImpl();
      return store.count();
    },
    async listArticles() {
      const store = await _getImpl();
      return store.list();
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
