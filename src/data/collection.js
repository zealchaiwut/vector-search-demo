/**
 * Milvus-backed vector collection for the vector-search-demo.
 * All exports are async — callers must await them.
 */

const COLLECTION_NAME = "documents";
const EMBEDDING_DIM = 384;

async function getClient() {
  const { MilvusClient } = await import("@zilliz/milvus2-sdk-node");
  const host = process.env.MILVUS_HOST || "localhost";
  const port = process.env.MILVUS_PORT || "19530";
  return new MilvusClient({ address: `${host}:${port}` });
}

export async function createCollection(recreate = false) {
  const { DataType } = await import("@zilliz/milvus2-sdk-node");
  const client = await getClient();

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
}

export async function dropCollection() {
  const client = await getClient();
  const { value: exists } = await client.hasCollection({
    collection_name: COLLECTION_NAME,
  });
  if (exists) {
    await client.dropCollection({ collection_name: COLLECTION_NAME });
  }
}

export async function upsertRows(rows) {
  if (!rows || rows.length === 0) return;
  const client = await getClient();
  await client.upsert({ collection_name: COLLECTION_NAME, data: rows });
}

export const insertRows = upsertRows;

export async function entityCount() {
  const client = await getClient();
  const result = await client.getCollectionStatistics({
    collection_name: COLLECTION_NAME,
  });
  const stat = (result.stats || []).find((s) => s.key === "row_count");
  return parseInt(stat?.value ?? "0", 10);
}

export async function listArticles() {
  const client = await getClient();
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
}

export async function getArticle(articleId) {
  const client = await getClient();
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
}

export async function deleteArticle(articleId) {
  const client = await getClient();
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
}
