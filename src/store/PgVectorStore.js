import pg from "pg";
import pgvector from "pgvector/pg";
import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const { Pool } = pg;
const __dirname = dirname(fileURLToPath(import.meta.url));
const MIGRATION_SQL = readFileSync(
  join(__dirname, "migrations", "001_articles.sql"),
  "utf8"
);

export class PgVectorStore {
  constructor(connectionString, table = "articles") {
    this._pool = new Pool({ connectionString });
    this._registered = false;
    this._table = table;
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

  async dropTable() {
    await this._pool.query(`DROP TABLE IF EXISTS ${this._table}`);
  }

  async migrate() {
    await this._pool.query(MIGRATION_SQL);
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
      const vec = pgvector.toSql(row.embedding);
      await this._pool.query(
        `INSERT INTO articles (id, headline, details, attachment_url, embedding)
         VALUES ($1, $2, $3, $4, $5)
         ON CONFLICT (id) DO UPDATE
           SET headline       = EXCLUDED.headline,
               details        = EXCLUDED.details,
               attachment_url = EXCLUDED.attachment_url,
               embedding      = EXCLUDED.embedding`,
        [row.id, row.headline, row.details, row.attachment_url ?? null, vec]
      );
    }
  }

  async delete(id) {
    const result = await this._pool.query(
      "DELETE FROM articles WHERE id = $1",
      [id]
    );
    return (result.rowCount ?? 0) > 0;
  }

  async search(embedding, limit = 10) {
    await this._register();
    const vec = pgvector.toSql(embedding);
    const result = await this._pool.query(
      `SELECT id, headline, details, attachment_url,
              1 - (embedding <=> $1) AS score
       FROM articles
       ORDER BY embedding <=> $1
       LIMIT $2`,
      [vec, limit]
    );
    return result.rows.map((row) => ({
      id: row.id,
      headline: row.headline,
      details: row.details,
      attachment_url: row.attachment_url,
      score: parseFloat(row.score),
    }));
  }

  async count() {
    const result = await this._pool.query("SELECT COUNT(*) FROM articles");
    return parseInt(result.rows[0].count, 10);
  }

  async list() {
    const result = await this._pool.query(
      "SELECT id, headline, details, attachment_url FROM articles ORDER BY id"
    );
    return result.rows;
  }

  async get(id) {
    const result = await this._pool.query(
      "SELECT id, headline, details, attachment_url FROM articles WHERE id = $1",
      [id]
    );
    return result.rows[0] ?? null;
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
