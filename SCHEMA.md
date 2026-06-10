# Schema

## Milvus Collection: `documents`

Defined in `src/milvus/schema.ts`.

| Field | Type | Details |
|-------|------|---------|
| `id` | VarChar(128) | Primary key, manually set (format: `<uuid>:<chunk_index>`) |
| `headline` | VarChar(1024) | Article headline |
| `details` | VarChar(65535) | Article body / chunk text |
| `attachment_url` | VarChar(512) | External attachment URL (http/https) |
| `embedding` | FloatVector(384) | MiniLM embedding vector |

### Vector Index

| Parameter | Value |
|-----------|-------|
| Index type | HNSW |
| Metric | COSINE |
| M | 16 |
| efConstruction | 200 |
