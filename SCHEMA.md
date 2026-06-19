# Schema

## Milvus Collection: `documents`

Defined in `src/milvus/schema.ts`.

| Field | Type | Details |
|-------|------|---------|
| `id` | VarChar(128) | Primary key, manually set (format: `<uuid>:<chunk_index>`) |
| `headline` | VarChar(1024) | Article headline |
| `details` | VarChar(65535) | Article body / chunk text |
| `attachment_url` | VarChar(512) | Attachment URL: `http(s)://` external links, `/uploads/` paths (PDF uploads), or `/download/` paths (ingested articles) |
| `embedding` | FloatVector(384) | MiniLM embedding vector |

### Vector Index

| Parameter | Value |
|-----------|-------|
| Index type | HNSW |
| Metric | COSINE |
| M | 16 |
| efConstruction | 200 |

## Postgres Table: `articles` (pgvector backend)

Defined in `src/store/migrations/001_articles.sql`. Applied automatically by `commander init` when `DB_BACKEND=postgres`.

| Column | Type | Details |
|--------|------|---------|
| `id` | text | Primary key (format: `<uuid>:<chunk_index>`) |
| `headline` | text | Article headline (NOT NULL) |
| `details` | text | Article body / chunk text (NOT NULL) |
| `attachment_url` | text | Attachment URL: `http(s)://` external links, `/uploads/` paths, or `/download/` paths (nullable) |
| `embedding` | vector(384) | MiniLM embedding vector (pgvector) |
| `created_at` | timestamptz | Row creation timestamp (default: now()) |

### Vector Index

| Parameter | Value |
|-----------|-------|
| Index type | HNSW |
| Operator class | vector_cosine_ops |
| Index name | `articles_embedding_hnsw_idx` |
