/**
 * Vector collection — backed by Milvus when MILVUS_HOST is set, otherwise
 * backed by collection.json for local development without a live Milvus instance.
 * All exports are async.
 */

import { writeFileSync, readFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const COLLECTION_PATH = join(__dirname, "..", "..", "collection.json");
const COLLECTION_NAME = "documents";
const EMBEDDING_DIM = 384;

// ── Milvus helpers ──────────────────────────────────────────────────────────

async function getMilvusClient() {
  const { MilvusClient } = await import("@zilliz/milvus2-sdk-node");
  const host = process.env.MILVUS_HOST;
  const port = process.env.MILVUS_PORT || "19530";
  return new MilvusClient({ address: `${host}:${port}` });
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
  if (process.env.MILVUS_HOST) {
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
  if (process.env.MILVUS_HOST) {
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
  if (process.env.MILVUS_HOST) {
    const client = await getMilvusClient();
    await client.upsert({ collection_name: COLLECTION_NAME, data: rows });
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
  if (process.env.MILVUS_HOST) {
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
  if (process.env.MILVUS_HOST) {
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
  if (process.env.MILVUS_HOST) {
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
  if (process.env.MILVUS_HOST) {
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
    return true;
  } else {
    const existing = fileLoad();
    const remaining = existing.filter((r) => r.id.split(":")[0] !== articleId);
    if (remaining.length === existing.length) return false;
    filePersist(remaining);
    return true;
  }
}
