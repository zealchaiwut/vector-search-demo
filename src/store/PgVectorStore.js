import pg from "pg";
import pgvector from "pgvector/pg";
import { readFileSync, readdirSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

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
