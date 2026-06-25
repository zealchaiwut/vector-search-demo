# Schema

## Milvus Collection: `documents`

Defined in `src/milvus/schema.ts`.

| Field | Type | Details |
|-------|------|---------|
| `id` | VarChar(128) | Primary key, manually set (format: `<uuid>:<chunk_index>`) |
| `headline` | VarChar(1024) | Article headline |
| `details` | VarChar(65535) | Article body / chunk text |
| `attachment_url` | VarChar(512) | Attachment URL: `http(s)://` external links, `/uploads/` paths (PDF uploads), or `/download/` paths (ingested articles) |
| `embedding` | FloatVector(384) | multilingual-e5-small embedding vector (passage prefixed with `"passage: "`) |

### Vector Index

| Parameter | Value |
|-----------|-------|
| Index type | HNSW |
| Metric | COSINE |
| M | 16 |
| efConstruction | 200 |

## Postgres Table: `articles` (pgvector backend)

Defined in `src/store/migrations/001_articles.sql` (initial) and `002_chunk_columns.sql` (chunk columns). Applied automatically by `commander init` when `DB_BACKEND=postgres`.

Each row is one chunk of an article. Multiple rows share the same `article_id`.

| Column | Type | Details |
|--------|------|---------|
| `id` | text | Primary key (format: `<uuid>:<chunk_index>`) |
| `article_id` | text | Article-level identifier (bare UUID, shared across all chunks) |
| `chunk_index` | integer | Zero-based position of this chunk within the article |
| `headline` | text | Article headline (NOT NULL) |
| `details` | text | Chunk text (NOT NULL) |
| `attachment_url` | text | Attachment URL: `http(s)://` external links, `/uploads/` paths, or `/download/` paths (nullable) |
| `embedding` | vector(384) | multilingual-e5-small embedding vector for this chunk (pgvector); text prefixed with `"passage: "` before embedding |
| `created_at` | timestamptz | Row creation timestamp (default: now()) |

### Vector Index

| Parameter | Value |
|-----------|-------|
| Index type | HNSW |
| Operator class | vector_cosine_ops |
| Index name | `articles_embedding_hnsw_idx` |

### Full-Text Search Column and Index

Added by `src/store/migrations/003_tsvector.sql`. Powers `GET /search/exact` via `plainto_tsquery` + `ts_rank`.

| Column | Type | Details |
|--------|------|---------|
| `ts` | tsvector | Generated column: `to_tsvector('english', headline \|\| ' ' \|\| details)`, stored |

| Parameter | Value |
|-----------|-------|
| Index type | GIN |
| Index name | `articles_ts_gin_idx` |
| Indexed column | `ts` |

### Trigram Index for Lexical Search

Added by `src/store/migrations/004_trgm.sql`. Powers trigram-based lexical search for Thai and other unspaced scripts via the `pg_trgm` extension.

| Parameter | Value |
|-----------|-------|
| Extension | `pg_trgm` |
| Index type | GIN |
| Index name | `articles_details_trgm_idx` |
| Indexed column | `details gin_trgm_ops` |

## Postgres Table: `model_meta`

Defined in `src/store/migrations/005_model_meta.sql`. Tracks the active embedding model and dimension to detect mismatches before they corrupt vector search. Applied automatically by `commander init` when `DB_BACKEND=postgres`.

| Column | Type | Details |
|--------|------|---------|
| `id` | integer | Primary key; constrained to 1 (singleton row) |
| `model_name` | text | Active embedding model name (NOT NULL) |
| `dim` | integer | Vector dimension for the active model (NOT NULL) |
| `updated_at` | timestamptz | Last update timestamp (default: now()) |

## Embedding Model Configuration

### Selecting a model

Set `EMBEDDING_MODEL` in your `.env` (or environment). Accepted values:

| Model name | Xenova ID | Dimension | Sparse |
|------------|-----------|-----------|--------|
| `Xenova/multilingual-e5-small` | same | 384 | no |
| `multilingual-e5-base` | `Xenova/multilingual-e5-base` | 768 | no |
| `multilingual-e5-large` | `Xenova/multilingual-e5-large` | 1024 | no |
| `BAAI/bge-m3` | `Xenova/bge-m3` | 1024 | yes |
| `Xenova/all-MiniLM-L6-v2` | same | 384 | no |

The `DIM` env var is **no longer required** — the dimension is automatically derived from the model name via `src/embeddings/model-registry.js`.

### Migration when changing models (postgres backend)

Changing `EMBEDDING_MODEL` to one with a **different dimension** requires a full re-embed. The postgres backend tracks the active model in the `model_meta` table (migration 005). On startup or upsert, `PgVectorStore.checkSchemaCompatibility()` compares the configured dimension against the stored one and raises a clear error if they differ.

**Migration steps (postgres):**

1. Set the new `EMBEDDING_MODEL` in `.env`.
2. Run:
   ```
   commander re-embed --recreate
   ```
   This drops and recreates the `articles` table with the new `vector(N)` column, then re-embeds all stored documents with the new model. The `model_meta` row is updated automatically.
3. Search will immediately use the new model and dimension.

> **Warning:** `--recreate` drops and recreates the `articles` table. All existing vectors are regenerated; no raw text is lost (it is saved before the drop). Always run against a backup in production.

**No migration needed** when switching between models of the **same dimension** (e.g. `multilingual-e5-small` ↔ `all-MiniLM-L6-v2`, both 384-dim). Just run `commander re-embed` without `--recreate`.

### BGE-M3 sparse vectors

When `EMBEDDING_MODEL=BAAI/bge-m3`, `batchEmbed` generates both dense (1024-dim) and sparse (lexical token weights) vectors. Sparse vectors are stored in the `sparse_embedding` field of each chunk (mock backend: JSON field in `collection.json`; postgres backend: future `sparse_embedding` jsonb column). They are used as the lexical component in hybrid search.

### Mock backend (collection.json)

The mock backend stores raw JSON. Re-embedding with a model of a different dimension works without `--recreate` because the JSON is schema-free. Simply run:
```
commander re-embed
```
and `collection.json` is rewritten with the new vectors.
