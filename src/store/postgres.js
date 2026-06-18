/**
 * Postgres VectorStore stub.
 * The connection and schema are not yet wired; all operations throw a clear
 * "not yet implemented" error so the backend is recognised by the factory
 * but fails fast with an actionable message rather than silently misbehaving.
 */

function notImplemented(op) {
  throw new Error(
    `[backend] postgres: "${op}" is not yet implemented. ` +
      "Set DB_BACKEND=milvus or DB_BACKEND=mock to use a working backend."
  );
}

export function getPostgresStore() {
  return {
    async createCollection() { notImplemented("createCollection"); },
    async dropCollection()   { notImplemented("dropCollection"); },
    async upsertRows()       { notImplemented("upsertRows"); },
    async entityCount()      { notImplemented("entityCount"); },
    async listArticles()     { notImplemented("listArticles"); },
    async search()           { notImplemented("search"); },
    async ping()             { notImplemented("ping"); },
  };
}
