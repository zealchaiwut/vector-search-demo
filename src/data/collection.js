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
const COLLECTION_NAME = "documents";
const EMBEDDING_DIM = 384;

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

async function getMilvusClient() {
  const { MilvusClient } = await import("@zilliz/milvus2-sdk-node");
  return new MilvusClient({ address: milvusAddress() });
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
    await store._query("DROP TABLE IF EXISTS articles");
    return;
  }
  if (useMilvus()) {
    const client = await getMilvusClient();
    const { value: exists } = await client.hasCollection({
      collection_name: COLLECTION_NAME,
    });
    if (exists) {
      await client.dropCollection({ collection_name: COLLECTION_NAME });
    }
  } else {
    if (existsSync(COLLECTION_PATH)) {
      writeFileSync(COLLECTION_PATH, "[]", "utf8");
    }
  }
}

export async function createCollection(recreate = false) {
  if (usePostgres()) {
    const store = await getPgStore();
    if (recreate) await store._query("DROP TABLE IF EXISTS articles");
    await store.migrate();
    return;
  }
  if (useMilvus()) {
    const { DataType } = await import("@zilliz/milvus2-sdk-node");
    const client = await getMilvusClient();

    const { value: exists } = await client.hasCollection({
      collection_name: COLLECTION_NAME,
    });

    if (exists) {
      if (!recreate) return;
      await client.dropCollection({ collection_name: COLLECTION_NAME });
    }

    await client.createCollection({
      collection_name: COLLECTION_NAME,
      fields: [
        {
          name: "id",
          data_type: DataType.VarChar,
          max_length: 128,
          is_primary_key: true,
          autoID: false,
        },
        { name: "headline", data_type: DataType.VarChar, max_length: 1024 },
        { name: "details", data_type: DataType.VarChar, max_length: 65535 },
        { name: "attachment_url", data_type: DataType.VarChar, max_length: 512 },
        { name: "embedding", data_type: DataType.FloatVector, dim: EMBEDDING_DIM },
      ],
    });

    await client.createIndex({
      collection_name: COLLECTION_NAME,
      field_name: "embedding",
      index_type: "HNSW",
      metric_type: "COSINE",
      params: { M: 16, efConstruction: 200 },
    });

    await client.loadCollection({ collection_name: COLLECTION_NAME });
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
    const client = await getMilvusClient();
    await client.upsert({ collection_name: COLLECTION_NAME, data: rows });
    await client.flush({ collection_names: [COLLECTION_NAME] });
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
    const client = await getMilvusClient();
    const result = await client.getCollectionStatistics({
      collection_name: COLLECTION_NAME,
    });
    const stat = (result.stats || []).find((s) => s.key === "row_count");
    return parseInt(stat?.value ?? "0", 10);
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
    const client = await getMilvusClient();
    const result = await client.query({
      collection_name: COLLECTION_NAME,
      filter: 'id like "%"',
      output_fields: ["id", "headline", "details", "attachment_url"],
      limit: 16384,
    });
    const rows = result.data || [];
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
    const client = await getMilvusClient();
    const result = await client.query({
      collection_name: COLLECTION_NAME,
      filter: `id like "${articleId}:%"`,
      output_fields: ["id", "headline", "details", "attachment_url"],
      limit: 1,
    });
    const rows = result.data || [];
    if (rows.length === 0) return null;
    const row = rows[0];
    return {
      id: articleId,
      headline: row.headline,
      details: row.details,
      attachment_url: row.attachment_url,
    };
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
    const client = await getMilvusClient();
    const check = await client.query({
      collection_name: COLLECTION_NAME,
      filter: `id like "${articleId}:%"`,
      output_fields: ["id"],
      limit: 1,
    });
    if ((check.data || []).length === 0) return false;
    await client.delete({
      collection_name: COLLECTION_NAME,
      filter: `id like "${articleId}:%"`,
    });
    // Seal the segment so the delete is visible to immediate queries/searches.
    await client.flushSync({ collection_names: [COLLECTION_NAME] });
    return true;
  } else {
    const existing = fileLoad();
    const remaining = existing.filter((r) => r.id.split(":")[0] !== articleId);
    if (remaining.length === existing.length) return false;
    filePersist(remaining);
    return true;
  }
}
