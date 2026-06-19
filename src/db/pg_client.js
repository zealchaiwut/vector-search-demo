import pg from "pg";

const { Pool } = pg;

let _client = null;

class PgClientWrapper {
  constructor() {
    this._pool = null;
  }

  _createPool() {
    return new Pool({
      host: process.env.POSTGRES_HOST || "localhost",
      port: parseInt(process.env.POSTGRES_PORT || "5432", 10),
      database: process.env.POSTGRES_DB || "vectordb",
      user: process.env.POSTGRES_USER || "vectoruser",
      password: process.env.POSTGRES_PASSWORD || "vectorpass",
    });
  }

  async _init() {
    if (this._pool) return;
    this._pool = this._createPool();
    // Enable pgvector extension on first connection
    await this._pool.query("CREATE EXTENSION IF NOT EXISTS vector;");
  }

  async checkHealth() {
    await this._init();
    const res = await this._pool.query(
      "SELECT extname FROM pg_extension WHERE extname = 'vector';"
    );
    const row = res.rows[0];
    return row ? row.extname : null;
  }

  async end() {
    if (this._pool) {
      await this._pool.end();
      this._pool = null;
    }
  }
}

export function getPgClient() {
  if (!_client) {
    _client = new PgClientWrapper();
  }
  return _client;
}
