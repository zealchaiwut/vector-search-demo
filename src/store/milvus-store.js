/**
 * MilvusStore — VectorStore implementation backed by a live Milvus instance.
 *
 * This is the ONLY file in the project that imports @zilliz/milvus2-sdk-node.
 * All other modules reach Milvus exclusively through this class via getStore().
 */

import { getArticleIdError } from "../data/articleValidation.js";

const COLLECTION_NAME = "documents";
const EMBEDDING_DIM = 384;
// HNSW expansion factor: fetch more candidates than k before collapsing by article.
const EF = 64;

export class MilvusStore {
  constructor(address) {
    this._address = address;
    this._sdk = null;
  }

  async _client() {
    if (!this._sdk) {
      const { MilvusClient } = await import("@zilliz/milvus2-sdk-node");
      this._sdk = new MilvusClient({ address: this._address });
    }
    return this._sdk;
  }

  // ---------------------------------------------------------------------------
  // Setup
  // ---------------------------------------------------------------------------

  async init(recreate = false) {
    const { DataType } = await import("@zilliz/milvus2-sdk-node");
    const client = await this._client();

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

  // migrate is an alias for init (creates schema if not present)
  async migrate() {
    return this.init();
  }

  async drop() {
    const client = await this._client();
    const { value: exists } = await client.hasCollection({
      collection_name: COLLECTION_NAME,
    });
    if (exists) {
      await client.dropCollection({ collection_name: COLLECTION_NAME });
    }
  }

  // ---------------------------------------------------------------------------
  // Data operations
  // ---------------------------------------------------------------------------

  async upsert(rows) {
    if (!rows || rows.length === 0) return;
    const client = await this._client();
    await client.upsert({ collection_name: COLLECTION_NAME, data: rows });
    await client.flush({ collection_names: [COLLECTION_NAME] });
  }

  async delete(articleId) {
    const idError = getArticleIdError(articleId);
    if (idError) throw new Error(idError);

    const client = await this._client();
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
  }

  async count() {
    const client = await this._client();
    const result = await client.getCollectionStatistics({
      collection_name: COLLECTION_NAME,
    });
    const stat = (result.stats || []).find((s) => s.key === "row_count");
    return parseInt(stat?.value ?? "0", 10);
  }

  // ---------------------------------------------------------------------------
  // Query operations
  // ---------------------------------------------------------------------------

  async search(queryVector, k) {
    const client = await this._client();

    let searchResult;
    try {
      searchResult = await client.search({
        collection_name: COLLECTION_NAME,
        data: [queryVector],
        output_fields: ["id", "headline", "details", "attachment_url"],
        limit: EF,
        params: { ef: EF },
        consistency_level: "Strong",
      });
    } catch (err) {
      const message = String(err?.message ?? err);
      const isExpected =
        /collection.*(not found|doesn'?t exist|not exist)/i.test(message) ||
        /COLLECTION_NOT_EXIST/i.test(message) ||
        err?.code === 25;

      console.error(
        `[MilvusStore.search] error (expected=${isExpected}): ${message}`
      );

      if (isExpected) return [];
      throw err;
    }

    const hits = searchResult.results || [];
    if (hits.length === 0) return [];

    // Return raw chunk hits; grouping by parent article is the caller's responsibility
    // (mirrors PgVectorStore which also returns flat chunk rows).
    return hits.map((hit) => ({
      id: hit.id,
      headline: hit.headline,
      details: hit.details,
      attachment_url: hit.attachment_url,
      score: hit.score,
    }));
  }

  async listArticles() {
    const client = await this._client();
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

  async getArticle(articleId) {
    const idError = getArticleIdError(articleId);
    if (idError) throw new Error(idError);

    const client = await this._client();
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

  // ---------------------------------------------------------------------------
  // Health
  // ---------------------------------------------------------------------------

  async ping() {
    const client = await this._client();
    const res = await client.getVersion();
    return res.version || res.Version || String(res);
  }

  getAddress() {
    return this._address;
  }
}
