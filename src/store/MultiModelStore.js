/**
 * MultiModelStore — file-backed store for per-chunk, per-model dense embeddings.
 *
 * Used by the mock backend (DB_BACKEND=mock) to persist vectors produced by
 * `embed-corpus --model <name>` and to serve model-targeted search queries.
 *
 * Backed by a single JSON file (default: chunk_embeddings.json at repo root).
 * Each entry is keyed by (chunk_id, model_id); the array contains:
 *   { chunk_id, model_id, vector: number[], dimension: number }
 *
 * For the Postgres backend, the equivalent is the chunk_embeddings table
 * (migration 007).
 */

import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const DEFAULT_PATH = join(__dirname, "..", "..", "chunk_embeddings.json");

function dotProduct(a, b) {
  let sum = 0;
  const len = Math.min(a.length, b.length);
  for (let i = 0; i < len; i++) sum += a[i] * b[i];
  return sum;
}

export class MultiModelStore {
  constructor(filePath) {
    this._path = filePath ?? DEFAULT_PATH;
  }

  _load() {
    if (!existsSync(this._path)) return [];
    try {
      const rows = JSON.parse(readFileSync(this._path, "utf8"));
      return Array.isArray(rows) ? rows : [];
    } catch {
      return [];
    }
  }

  _save(rows) {
    writeFileSync(this._path, JSON.stringify(rows), "utf8");
  }

  /**
   * Upsert a per-model vector for a chunk. Idempotent: replaces the existing
   * entry for the same (chunk_id, model_id) pair.
   *
   * @param {string} chunkId   Chunk row id (e.g. "article-1:0")
   * @param {string} modelId   Model name (e.g. "BAAI/bge-m3")
   * @param {number[]} vector  Dense float vector
   * @param {number} dimension Vector length
   */
  async upsert(chunkId, modelId, vector, dimension) {
    const rows = this._load();
    const idx = rows.findIndex(
      (r) => r.chunk_id === chunkId && r.model_id === modelId
    );
    const entry = { chunk_id: chunkId, model_id: modelId, vector, dimension };
    if (idx >= 0) {
      rows[idx] = entry;
    } else {
      rows.push(entry);
    }
    this._save(rows);
  }

  /**
   * Retrieve the stored entry for (chunkId, modelId), or null if absent.
   *
   * @param {string} chunkId
   * @param {string} modelId
   * @returns {Promise<{chunk_id, model_id, vector, dimension}|null>}
   */
  async get(chunkId, modelId) {
    const rows = this._load();
    return rows.find((r) => r.chunk_id === chunkId && r.model_id === modelId) ?? null;
  }

  /**
   * List all stored entries for a given model.
   *
   * @param {string} modelId
   * @returns {Promise<Array<{chunk_id, model_id, vector, dimension}>>}
   */
  async list(modelId) {
    const rows = this._load();
    return rows.filter((r) => r.model_id === modelId);
  }

  /**
   * Search for the most relevant articles given a query vector and model.
   * Ranks by cosine similarity (dot product on pre-normalised vectors).
   * Groups chunks by article, keeping the best-scoring chunk per article.
   *
   * @param {number[]} queryVector  Dense query embedding (same model as modelId)
   * @param {string} modelId        Model whose vectors to use
   * @param {number} k              Max results
   * @param {Array<{id: string, headline: string, details: string, attachment_url: ?string}>} articleRows
   *   All chunk rows from the main collection (used to resolve article metadata).
   * @returns {Promise<Array<{id, headline, details, score, attachment_url}>>}
   */
  async search(queryVector, modelId, k, articleRows) {
    const embeddings = await this.list(modelId);
    if (embeddings.length === 0) return [];

    const rowById = new Map(articleRows.map((r) => [r.id, r]));

    const scored = embeddings.map((e) => {
      const row = rowById.get(e.chunk_id);
      const articleId = e.chunk_id.split(":")[0];
      return {
        chunk_id: e.chunk_id,
        articleId,
        score: dotProduct(queryVector, e.vector),
        headline: row?.headline ?? "",
        details: row?.details ?? "",
        attachment_url: row?.attachment_url ?? null,
      };
    });

    // Collapse to best-scoring chunk per article
    const byArticle = new Map();
    for (const item of scored) {
      const existing = byArticle.get(item.articleId);
      if (!existing || item.score > existing.score) {
        byArticle.set(item.articleId, item);
      }
    }

    return [...byArticle.values()]
      .sort((a, b) => b.score - a.score)
      .slice(0, k)
      .map((r) => ({
        id: r.articleId,
        headline: r.headline,
        details: r.details,
        score: parseFloat(r.score.toFixed(4)),
        attachment_url: r.attachment_url,
      }));
  }
}

let _store = null;

/**
 * Return the singleton MultiModelStore for the mock backend.
 * Override the backing file via MULTI_MODEL_STORE_PATH env var.
 */
export function getMultiModelStore() {
  if (!_store) {
    const path = process.env.MULTI_MODEL_STORE_PATH ?? DEFAULT_PATH;
    _store = new MultiModelStore(path);
  }
  return _store;
}
