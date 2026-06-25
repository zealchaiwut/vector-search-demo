import pg from "pg";
import pgvector from "pgvector/pg";
import { readFileSync, readdirSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { EMBEDDING_DIM, EMBEDDING_MODEL } from "../embeddings/index.js";

const { Pool } = pg;
const __dirname = dirname(fileURLToPath(import.meta.url));
const MIGRATIONS_DIR = join(__dirname, "migrations");

function loadMigrations() {
  return readdirSync(MIGRATIONS_DIR)
    .filter((f) => f.endsWith(".sql"))
    .sort()
    .map((f) => readFileSync(join(MIGRATIONS_DIR, f), "utf8"));
}

export class PgVectorStore {
  constructor(connectionString) {
    this._pool = new Pool({ connectionString });
    this._registered = false;
  }

  async _register() {
    if (this._registered) return;
    const client = await this._pool.connect();
    await pgvector.registerType(client);
    client.release();
    this._registered = true;
  }

  async _query(text, values) {
    return this._pool.query(text, values);
  }

  async migrate() {
    for (const sql of loadMigrations()) {
      await this._pool.query(sql);
    }
    await this._register();
  }

  /**
   * Check that the stored model_meta dimension matches the configured EMBEDDING_DIM.
   * If the model_meta table has a row with a different dimension, throws with migration instructions.
   * If no row exists yet, inserts the current model/dim.
   * Call after migrate() when doing any write operation.
   */
  async checkSchemaCompatibility() {
    const modelName = process.env.EMBEDDING_MODEL ?? EMBEDDING_MODEL;
    const dim = EMBEDDING_DIM;

    // Ensure the table exists (migration 005 must have run)
    let existing;
    try {
      existing = await this._pool.query("SELECT model_name, dim FROM model_meta WHERE id = 1");
    } catch {
      // model_meta table doesn't exist yet — migration hasn't run, skip check
      return;
    }

    if (existing.rows.length === 0) {
      // First use — record current model
      await this._pool.query(
        "INSERT INTO model_meta (id, model_name, dim) VALUES (1, $1, $2) ON CONFLICT (id) DO UPDATE SET model_name=$1, dim=$2, updated_at=now()",
        [modelName, dim]
      );
      return;
    }

    const stored = existing.rows[0];
    if (stored.dim !== dim) {
      throw new Error(
        `[dimension mismatch] The stored embedding schema uses dim=${stored.dim} ` +
          `(model: ${stored.model_name}), but the configured model "${modelName}" ` +
          `produces dim=${dim}.\n\n` +
          `Migration instructions:\n` +
          `  1. Ensure EMBEDDING_MODEL is set to your new model in .env.\n` +
          `  2. Run: commander re-embed --recreate\n` +
          `     This drops and recreates the articles table with the new dimension,\n` +
          `     then re-embeds all stored documents.\n` +
          `  See SCHEMA.md for the full migration guide.`
      );
    }

    // Model changed but dim same — update model name only
    if (stored.model_name !== modelName) {
      await this._pool.query(
        "UPDATE model_meta SET model_name=$1, updated_at=now() WHERE id=1",
        [modelName]
      );
    }
  }

  /**
   * Drop and recreate the articles table using the configured EMBEDDING_DIM.
   * Saves raw document text first, then re-inserts without embeddings.
   * Used by re-embed --recreate for dimension migration.
   * @returns {Promise<Array<object>>} saved rows (without embeddings)
   */
  async recreateWithNewDimension() {
    const dim = EMBEDDING_DIM;
    const modelName = process.env.EMBEDDING_MODEL ?? EMBEDDING_MODEL;

    // Save all existing raw data before dropping
    let savedRows = [];
    try {
      const result = await this._pool.query(
        "SELECT id, article_id, chunk_index, headline, details, attachment_url FROM articles ORDER BY article_id, chunk_index"
      );
      savedRows = result.rows;
    } catch {
      // table might not exist yet
    }

    // Drop and recreate the articles table with the new vector dimension
    await this._pool.query("DROP TABLE IF EXISTS articles CASCADE");
    await this._pool.query(`
      CREATE EXTENSION IF NOT EXISTS vector;
      CREATE TABLE articles (
        id             text PRIMARY KEY,
        headline       text NOT NULL,
        details        text NOT NULL,
        attachment_url text,
        article_id     text,
        chunk_index    integer DEFAULT 0,
        embedding      vector(${dim}),
        created_at     timestamptz DEFAULT now()
      );
      CREATE INDEX articles_embedding_hnsw_idx ON articles USING hnsw (embedding vector_cosine_ops);
      CREATE INDEX articles_article_id_idx ON articles (article_id);
    `);

    // Re-run remaining migrations (skip 001 which creates the table)
    const migrations = loadMigrations().filter(
      (sql) => !sql.includes("CREATE TABLE IF NOT EXISTS articles")
    );
    for (const sql of migrations) {
      try {
        await this._pool.query(sql);
      } catch {
        // idempotent migration may already apply
      }
    }

    // Update model_meta
    await this._pool.query(
      "INSERT INTO model_meta (id, model_name, dim) VALUES (1, $1, $2) ON CONFLICT (id) DO UPDATE SET model_name=$1, dim=$2, updated_at=now()",
      [modelName, dim]
    );

    await this._register();
    return savedRows;
  }

  async ping() {
    const result = await this._pool.query("SELECT NOW() AS ts");
    return result.rows[0].ts;
  }

  async upsert(rows) {
    if (!rows || rows.length === 0) return;
    await this._register();
    for (const row of rows) {
      const colonIdx = row.id.indexOf(":");
      const articleId = colonIdx >= 0 ? row.id.slice(0, colonIdx) : row.id;
      const chunkIndex = colonIdx >= 0 ? parseInt(row.id.slice(colonIdx + 1), 10) : 0;
      const vec = pgvector.toSql(row.embedding);
      await this._pool.query(
        `INSERT INTO articles (id, article_id, chunk_index, headline, details, attachment_url, embedding)
         VALUES ($1, $2, $3, $4, $5, $6, $7)
         ON CONFLICT (id) DO UPDATE
           SET article_id     = EXCLUDED.article_id,
               chunk_index    = EXCLUDED.chunk_index,
               headline       = EXCLUDED.headline,
               details        = EXCLUDED.details,
               attachment_url = EXCLUDED.attachment_url,
               embedding      = EXCLUDED.embedding`,
        [row.id, articleId, chunkIndex, row.headline, row.details, row.attachment_url ?? null, vec]
      );
    }
  }

  async delete(id) {
    const result = await this._pool.query(
      "DELETE FROM articles WHERE article_id = $1",
      [id]
    );
    return (result.rowCount ?? 0) > 0;
  }

  async search(embedding, limit = 10) {
    await this._register();
    const vec = pgvector.toSql(embedding);
    const result = await this._pool.query(
      `SELECT id, article_id, chunk_index, headline, details, attachment_url,
              1 - (embedding <=> $1) AS score
       FROM articles
       ORDER BY embedding <=> $1
       LIMIT $2`,
      [vec, limit]
    );
    return result.rows.map((row) => ({
      id: row.id,
      article_id: row.article_id,
      chunk_index: row.chunk_index,
      headline: row.headline,
      details: row.details,
      attachment_url: row.attachment_url,
      score: parseFloat(row.score),
    }));
  }

  async count() {
    const result = await this._pool.query(
      "SELECT COUNT(DISTINCT article_id) FROM articles"
    );
    return parseInt(result.rows[0].count, 10);
  }

  async chunkCount() {
    const result = await this._pool.query("SELECT COUNT(*) FROM articles");
    return parseInt(result.rows[0].count, 10);
  }

  async listChunks() {
    const result = await this._pool.query(
      "SELECT id, article_id, chunk_index, headline, details, attachment_url, embedding FROM articles ORDER BY article_id, chunk_index"
    );
    return result.rows.map((r) => ({
      id: r.id,
      article_id: r.article_id,
      chunk_index: r.chunk_index,
      headline: r.headline,
      details: r.details,
      attachment_url: r.attachment_url,
      embedding: r.embedding,
    }));
  }

  async list() {
    const result = await this._pool.query(
      `SELECT article_id AS id,
              (array_agg(headline ORDER BY chunk_index))[1] AS headline,
              (array_agg(attachment_url ORDER BY chunk_index))[1] AS attachment_url,
              string_agg(details, ' ' ORDER BY chunk_index) AS details
       FROM articles
       GROUP BY article_id
       ORDER BY article_id`
    );
    return result.rows;
  }

  async get(id) {
    const result = await this._pool.query(
      `SELECT id, article_id, chunk_index, headline, details, attachment_url
       FROM articles WHERE article_id = $1
       ORDER BY chunk_index ASC`,
      [id]
    );
    if (result.rows.length === 0) return null;
    const first = result.rows[0];
    const details = result.rows.map((r) => r.details).join(" ");
    return {
      id: first.article_id,
      headline: first.headline,
      details,
      attachment_url: first.attachment_url,
    };
  }

  async end() {
    await this._pool.end();
  }
}

let _store = null;

export function getPgStore() {
  if (!_store) {
    const url = process.env.DATABASE_URL;
    if (!url) throw new Error("DATABASE_URL is required for DB_BACKEND=postgres");
    _store = new PgVectorStore(url);
  }
  return _store;
}
