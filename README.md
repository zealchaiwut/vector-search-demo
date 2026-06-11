# vector-search-demo

A semantic document-search demo: a `commander` CLI plus a Fastify web server that
ingests documents, ranks them by similarity to a query, and serves the source files
for download. Includes a recall@k evaluation harness.

> **Note:** The first `ingest` run will download the embedding model (~90 MB) from
> HuggingFace. Subsequent runs reuse the cached model and are much faster.

## What's built / not built

### ✅ Built and verified end-to-end
- **CLI** (`init`, `ingest`, `search`, `serve`, `ping`) via `node dist/cli.js <cmd>`.
- **Ingestion pipeline** — a small built-in corpus (6 docs in `src/data/generator.js`)
  is chunked, embedded using MiniLM (384-dim neural vectors via `src/embeddings/index.js`),
  stored in Milvus (`MILVUS_HOST` set) or a local `collection.json` fallback, and saved
  as downloadable `.txt` files under `attachments/`.
- **Search** — `core/search.js` embeds the query with MiniLM and runs ANN search via
  Milvus (HNSW COSINE, EF=64 over-fetch, chunk collapsing per article) when
  `MILVUS_HOST` is set, or falls back to a linear cosine scan over `collection.json`.
- **HTTP API** — one Fastify server with `/health`, `/search`, `/download/:docId`
  (GET + HEAD), and the search UI at `/`.
- **Evaluation** — `npm run eval` reports recall@k against the running server.
  Current corpus + fixtures score **recall@5 = 1.00**.

### ❌ Not built / not wired (despite being present in the tree)
- **Corpus is a fixed built-in set**, not loaded from external files or a real data source.

## Prerequisites

- Node.js >= 18 (tested on 20+)
- Docker — only needed for the `ping` command / `milvus:up`; **not** required for search.

## Setup

```sh
npm install
cp .env.example .env
# Set the port. NOTE: on macOS, port 7000 is taken by AirPlay Receiver and
# 8000/8001 may be used by other tooling — pick a free port, e.g. 7070:
echo "PORT=7070" >> .env
npm run build
```

## Run it

```sh
node dist/cli.js init      # provision an empty, indexed (file-backed) collection
node dist/cli.js ingest    # index the built-in corpus -> collection.json + attachments/
node dist/cli.js serve     # start the web server (port from .env)
```

Then open the UI at `http://localhost:<PORT>` (e.g. http://localhost:7070), or:

```sh
curl localhost:7070/health
curl "localhost:7070/search?q=how%20do%20we%20restore%20a%20database%20backup"
curl -I localhost:7070/download/doc-004
node dist/cli.js search vector search pipeline   # CLI search
node dist/cli.js ping                            # check Milvus (requires milvus:up)
```

## CLI commands

```sh
node dist/cli.js init                 # create an empty, indexed collection
node dist/cli.js ingest               # ingest the built-in corpus
node dist/cli.js search <query...>    # search indexed documents (prints results)
node dist/cli.js serve                # start the Fastify server
node dist/cli.js ping                 # check Milvus connectivity (Docker required)
node dist/cli.js verify               # check vector/article count integrity
```

## npm scripts

| Script | Description |
|--------|-------------|
| `npm run build` | Compile TypeScript to `dist/` |
| `npm run dev` | Run server in watch mode (tsx) |
| `npm start` | Start compiled server (`node dist/cli.js serve`) |
| `npm run eval` | Run recall@k evaluation against the running server |
| `npm run milvus:up` | Start Milvus via Docker Compose (only used by `ping`) |
| `npm run milvus:down` | Stop Milvus |

## HTTP API

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Serve search UI (`public/index.html`) |
| `GET` | `/health` | `{"status":"ok"}` |
| `GET` | `/health/integrity` | Compare article count vs. vector count |
| `GET` | `/search?q=<query>&k=<n>` | Return top-k ranked result cards |
| `GET` / `HEAD` | `/download/:articleId` | Download the ingested source article as `.txt` |
| `POST` | `/articles` | Create a new article (validated) |
| `GET` | `/articles` | List all articles |
| `PUT` | `/articles/:id` | Update an existing article (validated) |
| `DELETE` | `/articles/:id` | Delete an article |
| `POST` | `/articles/bulk` | Bulk-create articles; atomically rejected if any item fails validation |

Search result shape (`GET /search`):

```json
{
  "results": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "headline": "...",
      "details": "...",
      "score": 0.1996,
      "attachment_url": "https://example.com/file.pdf",
      "best_passage": {
        "text": "Single verbatim sentence most similar to the query.",
        "start_offset": 42,
        "end_offset": 93
      }
    }
  ]
}
```

`attachment_url` is the external URL for the attachment; results where `attachment_url` is null/empty do not render a link in the UI. `best_passage` is the highest-scoring sentence from the article (cosine similarity against the query vector). `start_offset` / `end_offset` are character indices into the full article text.

Integrity check response (`GET /health/integrity`):

```json
{ "status": "ok", "articleCount": 42, "vectorCount": 42 }
// or when counts differ:
{ "status": "mismatch", "articleCount": 42, "vectorCount": 39, "delta": 3 }
```

## Evaluation

`npm run eval` hits the **running** server (`GET /search?q=`) with fixed query fixtures
and reports recall@k.

| Env var | Default | Description |
|---------|---------|-------------|
| `PORT` | `7070` | Used to derive the default `SEARCH_URL` |
| `SEARCH_URL` | `http://localhost:${PORT}/search` | Search API endpoint |
| `K` | `5` | Number of top results to check |
| `RECALL_THRESHOLD` | `0.8` | Minimum pass fraction (0.0–1.0) |

Exit code 0 when recall@k ≥ threshold.

## Configuration

Copy `.env.example` to `.env`.

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `8000` | Server port (override — see Setup note about 7000/8000) |
| `MILVUS_HOST` | (unset) | Milvus host — when set, all storage and search use Milvus |
| `MILVUS_PORT` | `19530` | Milvus gRPC port |
| `MILVUS_ADDRESS` | `localhost:19530` | Fallback gRPC address for `ping` and the schema helpers when `MILVUS_HOST`/`MILVUS_PORT` are unset |
| `COLLECTION_NAME` | `documents` | Milvus collection name |
| `EMBEDDING_MODEL` | `Xenova/all-MiniLM-L6-v2` | Embedding model used by `ingest`. The first ingest run downloads ~90 MB from HuggingFace; subsequent runs use the cached model. |
| `DIM` | `384` | Embedding dimension — must match the model output (384 for MiniLM). A mismatch raises a clear error at ingest time. |

## Architecture (current path)

```
src/data/generator.js   built-in 6-doc corpus
  -> src/data/chunker.js         split into chunks
  -> src/data/embedder.js        384-dim MiniLM vectors (via src/embeddings/index.js)
  -> src/data/collection.js  ->  Milvus (when MILVUS_HOST is set)
                             ->  collection.json (local fallback without Milvus)
  -> attachments/*.txt            downloadable source files

src/core/search.js   embeds query with MiniLM, queries Milvus (HNSW COSINE ANN)
                     or falls back to linear cosine scan over collection.json
src/milvus/client.js   singleton MilvusClient wrapper (dynamic SDK import)
src/milvus/schema.ts   Milvus collection schema: HNSW index, COSINE metric, dim=384
src/server.mjs       HTTP: /health, /search, /download, /articles CRUD
```
