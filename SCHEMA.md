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

Defined in `src/store/migrations/001_articles.sql` (initial), `002_chunk_columns.sql` (chunk columns with backfill), and `006_chunk_columns_notnull.sql` (NOT NULL enforcement). Applied automatically by `commander init` when `DB_BACKEND=postgres`.

Each row is one chunk of an article. Multiple rows share the same `article_id`.

| Column | Type | Details |
|--------|------|---------|
| `id` | text | Primary key (format: `<uuid>:<chunk_index>`) |
| `article_id` | text | Article-level identifier (bare UUID, shared across all chunks) (NOT NULL — enforced by migration 006) |
| `chunk_index` | integer | Zero-based position of this chunk within the article (NOT NULL — enforced by migration 006) |
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

Added by `src/store/migrations/003_tsvector.sql`. Powers `GET /search/exact` and the lexical component of hybrid search. As of sprint 16 (#187), queries use an OR-`tsquery` built from all whitespace-tokenised terms (e.g. `credit | card`) scored with `ts_rank_cd`, plus a proximity boost when the terms appear as an exact adjacent phrase (`phraseto_tsquery`). This preserves recall for multi-term queries instead of the implicit-AND behaviour of `plainto_tsquery`.

| Column | Type | Details |
|--------|------|---------|
| `ts` | tsvector | Generated column: `to_tsvector('english', headline \|\| ' ' \|\| details)`, stored |

| Parameter | Value |
|-----------|-------|
| Index type | GIN |
| Index name | `articles_ts_gin_idx` |
| Indexed column | `ts` |

### Simple-Dictionary FTS Column and Index (OR-tsquery / Thai)

Added by `src/store/migrations/008_or_rank.sql` (#187). The `simple` dictionary lowercases tokens without stemming, which suits English OR queries where exact token forms matter and Thai text pre-segmented into word tokens with `Intl.Segmenter` (`src/core/lexical/thaiSegmenter.js`). `PgVectorStore.upsert()` populates this column at ingest time (Thai text is word-segmented first); migration 008 back-fills existing rows. The OR-tsquery lexical scorer (`src/core/lexical/tsvectorOrScorer.js`) queries `ts` for English and `ts_simple` for Thai, falling back to pg_trgm `word_similarity` when `ts_simple` is unavailable.

| Column | Type | Details |
|--------|------|---------|
| `ts_simple` | tsvector | `to_tsvector('simple', headline \|\| ' ' \|\| details)`; Thai text is word-segmented before tokenisation |

| Parameter | Value |
|-----------|-------|
| Index type | GIN |
| Index name | `articles_ts_simple_gin_idx` |
| Indexed column | `ts_simple` |

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

## Postgres Table: `chunk_embeddings` (multi-model corpus comparison)

Defined in `src/store/migrations/007_chunk_embeddings.sql` (#187/#185). Stores per-chunk, per-model dense vectors so the same corpus can be indexed under multiple embedding models (e.g. 384-d `multilingual-e5-small` and 1024-d `BAAI/bge-m3`) simultaneously without schema changes. Vectors are stored as `real[]` (rather than `vector(N)`) so models with different output dimensions coexist; search computes cosine similarity in-process via a sequential scan. Populated by `embed-corpus --model <name>` and queried by `search --model <name>`. The mock backend stores the equivalent data in `chunk_embeddings.json` at the repo root (`src/store/MultiModelStore.js`).

| Column | Type | Details |
|--------|------|---------|
| `chunk_id` | text | Chunk row id (format: `<uuid>:<chunk_index>`); part of primary key |
| `model_id` | text | Embedding model name (e.g. `BAAI/bge-m3`); part of primary key |
| `vector` | real[] | Dense embedding for this chunk under this model |
| `dimension` | integer | Vector length (NOT NULL) |
| `created_at` | timestamptz | Row creation timestamp (default: now()) |

Primary key `(chunk_id, model_id)` makes `embed-corpus` idempotent (re-running upserts rather than duplicating). Index `chunk_embeddings_model_id_idx` on `model_id` speeds per-model scans.

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
