/**
 * PostgresStore — stub VectorStore implementation for PostgreSQL backend.
 *
 * All methods throw "not implemented" errors. This placeholder signals that
 * DB_BACKEND=postgres is a recognised value while the full implementation
 * is out of scope for this sprint.
 */

const NOT_IMPLEMENTED = "PostgresStore: not implemented";

export class PostgresStore {
  async init() {
    throw new Error(NOT_IMPLEMENTED);
  }

  async migrate() {
    throw new Error(NOT_IMPLEMENTED);
  }

  async drop() {
    throw new Error(NOT_IMPLEMENTED);
  }

  async upsert(_rows) {
    throw new Error(NOT_IMPLEMENTED);
  }

  async delete(_articleId) {
    throw new Error(NOT_IMPLEMENTED);
  }

  async count() {
    throw new Error(NOT_IMPLEMENTED);
  }

  async search(_queryVector, _k) {
    throw new Error(NOT_IMPLEMENTED);
  }

  async listArticles() {
    throw new Error(NOT_IMPLEMENTED);
  }

  async getArticle(_articleId) {
    throw new Error(NOT_IMPLEMENTED);
  }

  async ping() {
    throw new Error(NOT_IMPLEMENTED);
  }
}
