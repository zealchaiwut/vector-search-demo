/**
 * MockStore — in-memory VectorStore implementation for unit tests.
 *
 * Requires no live database connection. State is lost when the process exits.
 * Does NOT import the Milvus SDK.
 */

function dotProduct(a, b) {
  let sum = 0;
  for (let i = 0; i < a.length; i++) sum += a[i] * b[i];
  return sum;
}

export class MockStore {
  constructor() {
    // Map<rowId, row> where rowId is the full "articleId:chunk" id
    this._rows = new Map();
  }

  // ---------------------------------------------------------------------------
  // Setup
  // ---------------------------------------------------------------------------

  async init() {
    // No-op: in-memory store needs no schema setup.
  }

  async migrate() {
    return this.init();
  }

  async drop() {
    this._rows.clear();
  }

  // ---------------------------------------------------------------------------
  // Data operations
  // ---------------------------------------------------------------------------

  async upsert(rows) {
    if (!rows || rows.length === 0) return;
    for (const row of rows) {
      this._rows.set(row.id, { ...row });
    }
  }

  async delete(articleId) {
    let deleted = false;
    for (const [key] of this._rows) {
      if (key.split(":")[0] === articleId) {
        this._rows.delete(key);
        deleted = true;
      }
    }
    return deleted;
  }

  async count() {
    return this._rows.size;
  }

  // ---------------------------------------------------------------------------
  // Query operations
  // ---------------------------------------------------------------------------

  async search(queryVector, k) {
    const rows = [...this._rows.values()].filter(
      (r) => Array.isArray(r.embedding) && r.embedding.length > 0
    );

    if (rows.length === 0) return [];

    // Score all rows by cosine similarity (dot product on pre-normalised vectors).
    const scored = rows.map((row) => ({
      articleId: row.id.split(":")[0],
      id: row.id,
      headline: row.headline,
      details: row.details,
      attachment_url: row.attachment_url,
      score: dotProduct(queryVector, row.embedding),
    }));

    // Collapse: keep best-scoring chunk per article.
    const byArticleId = new Map();
    for (const item of scored) {
      if (!byArticleId.has(item.articleId) || item.score > byArticleId.get(item.articleId).score) {
        byArticleId.set(item.articleId, {
          id: item.articleId,
          headline: item.headline,
          details: item.details,
          attachment_url: item.attachment_url,
          score: item.score,
        });
      }
    }

    return [...byArticleId.values()]
      .sort((a, b) => b.score - a.score)
      .slice(0, k);
  }

  async listArticles() {
    const seen = new Map();
    for (const row of this._rows.values()) {
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
    for (const row of this._rows.values()) {
      if (row.id.split(":")[0] === articleId) {
        return {
          id: articleId,
          headline: row.headline,
          details: row.details,
          attachment_url: row.attachment_url,
        };
      }
    }
    return null;
  }

  // ---------------------------------------------------------------------------
  // Health
  // ---------------------------------------------------------------------------

  async ping() {
    return "mock";
  }
}
