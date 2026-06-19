/**
 * Vector collection — backed by Postgres/pgvector (DB_BACKEND=postgres),
 * Milvus (DATA_BACKEND=milvus or MILVUS_HOST set), or the file-backed mock
 * (collection.json) by default. See ./backend.js for the selector.
 * All exports are async.
 */

import { writeFileSync, readFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { validateArticleId } from "./articleValidation.js";
import { useMilvus, milvusAddress, usePostgres } from "./backend.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const COLLECTION_PATH = join(__dirname, "..", "..", "collection.json");

// ── Postgres helpers ─────────────────────────────────────────────────────────

async function getPgStore() {
  const { getPgStore: _get } = await import("../store/PgVectorStore.js");
  return _get();
}

// Average a set of float32 embedding vectors.
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

// Collapse chunk rows (id like "articleId:N") into one row per article.
function collapseToArticles(rows) {
  const byArticle = new Map();
  for (const row of rows) {
    const articleId = row.id.split(":")[0];
    if (!byArticle.has(articleId)) {
      byArticle.set(articleId, { id: articleId, headline: row.headline, attachment_url: row.attachment_url, detailParts: [], embeddings: [] });
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

// ── Milvus helpers ──────────────────────────────────────────────────────────

async function getMilvusStoreInstance() {
  const { MilvusStore } = await import("../store/milvus-store.js");
  return new MilvusStore(milvusAddress());
}

// ── File-backed helpers ─────────────────────────────────────────────────────

function fileLoad() {
  if (!existsSync(COLLECTION_PATH)) return [];
  try {
    const rows = JSON.parse(readFileSync(COLLECTION_PATH, "utf8"));
    return Array.isArray(rows) ? rows : [];
  } catch {
    return [];
  }
}

function filePersist(rows) {
  writeFileSync(COLLECTION_PATH, JSON.stringify(rows), "utf8");
}

// ── Exported API ────────────────────────────────────────────────────────────

export async function dropCollection() {
  if (usePostgres()) {
    const store = await getPgStore();
    await store.dropTable();
    return;
  }
  if (useMilvus()) {
    const store = await getMilvusStoreInstance();
    await store.drop();
  } else {
    if (existsSync(COLLECTION_PATH)) {
      writeFileSync(COLLECTION_PATH, "[]", "utf8");
    }
  }
}

export async function createCollection(recreate = false) {
  if (usePostgres()) {
    const store = await getPgStore();
    if (recreate) await store.dropTable();
    await store.migrate();
    return;
  }
  if (useMilvus()) {
    const store = await getMilvusStoreInstance();
    await store.init(recreate);
  } else {
    writeFileSync(COLLECTION_PATH, "[]", "utf8");
  }
}

export async function upsertRows(rows) {
  if (!rows || rows.length === 0) return;
  if (usePostgres()) {
    const store = await getPgStore();
    // Collapse chunks into one row per article for postgres storage.
    const articles = collapseToArticles(rows);
    await store.upsert(articles);
    return;
  }
  if (useMilvus()) {
    const store = await getMilvusStoreInstance();
    await store.upsert(rows);
  } else {
    const existing = fileLoad();
    const byId = new Map(existing.map((r) => [r.id, r]));
    for (const row of rows) {
      byId.set(row.id, row);
    }
    filePersist([...byId.values()]);
  }
}

export const insertRows = upsertRows;

export async function entityCount() {
  if (usePostgres()) {
    const store = await getPgStore();
    return store.count();
  }
  if (useMilvus()) {
    const store = await getMilvusStoreInstance();
    return store.count();
  } else {
    return fileLoad().length;
  }
}

export async function listArticles() {
  if (usePostgres()) {
    const store = await getPgStore();
    return store.list();
  }
  if (useMilvus()) {
    const store = await getMilvusStoreInstance();
    return store.listArticles();
  } else {
    const rows = fileLoad();
    const seen = new Map();
    for (const row of rows) {
      const articleId = row.id.split(":")[0];
      if (!seen.has(articleId)) {
        seen.set(articleId, {
          id: articleId,
          headline: row.headline,
          details: row.details,
          attachment_url: row.attachment_url,
        });
      }
    }
    return [...seen.values()];
  }
}

export async function getArticle(articleId) {
  const idError = validateArticleId(articleId);
  if (idError) throw new Error(idError);
  if (usePostgres()) {
    const store = await getPgStore();
    return store.get(articleId);
  }
  if (useMilvus()) {
    const store = await getMilvusStoreInstance();
    return store.getArticle(articleId);
  } else {
    const rows = fileLoad();
    const row = rows.find((r) => r.id.split(":")[0] === articleId);
    if (!row) return null;
    return {
      id: articleId,
      headline: row.headline,
      details: row.details,
      attachment_url: row.attachment_url,
    };
  }
}

export async function deleteArticle(articleId) {
  const idError = validateArticleId(articleId);
  if (idError) throw new Error(idError);
  if (usePostgres()) {
    const store = await getPgStore();
    return store.delete(articleId);
  }
  if (useMilvus()) {
    const store = await getMilvusStoreInstance();
    return store.delete(articleId);
  } else {
    const existing = fileLoad();
    const remaining = existing.filter((r) => r.id.split(":")[0] !== articleId);
    if (remaining.length === existing.length) return false;
    filePersist(remaining);
    return true;
  }
}
