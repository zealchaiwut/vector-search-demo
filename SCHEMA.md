# Schema

## Milvus Collection: `documents`

Defined in `src/milvus/schema.js`.

| Field | Type | Details |
|-------|------|---------|
| `id` | Int64 | Primary key, auto-generated |
| `doc_id` | VarChar(128) | Document identifier |
| `chunk_id` | Int64 | Chunk index within document |
| `title` | VarChar(1024) | Document title |
| `text` | VarChar(65535) | Chunk text content |
| `attachment_name` | VarChar(512) | Source filename |
| `embedding` | FloatVector(384) | MiniLM embedding vector |

### Vector Index

| Parameter | Value |
|-----------|-------|
| Index type | HNSW |
| Metric | COSINE |
| M | 16 |
| efConstruction | 200 |
