# vector-search-demo

A semantic document-search demo: a `commander` CLI plus a Fastify web server that
ingests documents, ranks them by similarity to a query, and serves the source files
for download. Includes a recall@k evaluation harness.

> **Note:** The first `ingest` run will download the embedding model (~90 MB) from
> HuggingFace. Subsequent runs reuse the cached model and are much faster.

## What's built / not built

### ✅ Built and verified end-to-end
- **CLI** (`init`, `ingest`, `search`, `serve`, `ping`) via `node dist/cli.js <cmd>`.
- **Ingestion pipeline** — a small built-in corpus (7 docs including a Thai article in
  `src/data/generator.js`) is chunked into overlapping 500-character windows (100-char
  overlap, character-based for Thai compatibility), embedded using multilingual-e5-small
  (384-dim, `src/embeddings/index.js`), stored in Milvus (`MILVUS_HOST` set) or a local
  `collection.json` fallback, and saved as downloadable `.txt` files under `attachments/`.
- **Search** — `core/search.js` embeds the query with the `query:` e5 instruction prefix and
  runs ANN search via Milvus (HNSW COSINE, EF=64 over-fetch, chunk collapsing per article)
  when `MILVUS_HOST` is set, or falls back to a linear cosine scan over `collection.json`.
  Each result includes a `passages` array (top-scoring deduplicated chunks with per-chunk
  scores) and a `chunks` array (all matched chunks for the article, each with `text` and
  `score`) in addition to `best_passage`.
- **Exact/keyword search** — `GET /search/exact` runs Postgres FTS (`plainto_tsquery` +
  `ts_rank` over a GIN-indexed `tsvector` column). Only active when `DB_BACKEND=postgres`.
- **Compare tab** — the search UI has a side-by-side tab that runs both semantic and
  keyword searches simultaneously, with matched term highlighting.
- **Chunk-granularity Postgres storage** — the Postgres backend (`DB_BACKEND=postgres`)
  stores one row per chunk (sharing `article_id`), with a generated `tsvector` column for
  full-text search (migration `003_tsvector.sql`).
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
node dist/cli.js re-embed             # recompute embeddings for all existing articles/chunks
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
| `GET` | `/search?q=<query>&k=<n>` | Return top-k ranked result cards (semantic) |
| `GET` | `/search/exact?q=<query>&k=<n>` | Return top-k keyword results via Postgres FTS (`DB_BACKEND=postgres` only) |
| `GET` / `HEAD` | `/download/:articleId` | Download the ingested source article as `.txt` |
| `POST` | `/articles` | Create a new article (validated) |
| `GET` | `/articles` | List all articles |
| `PUT` | `/articles/:id` | Update an existing article (validated) |
| `DELETE` | `/articles/:id` | Delete an article |
| `POST` | `/articles/bulk` | Bulk-create articles; atomically rejected if any item fails validation |
| `POST` | `/api/upload-pdf` | Upload a PDF (multipart/form-data); extract text (with Thai OCR fallback) and return pre-populated article JSON (`headline`, `details`, `attachment_url`) |
| `GET` | `/uploads/:filename` | Serve a stored PDF that was uploaded via `/api/upload-pdf` |

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
      "attachment_url_type": "external",
      "best_passage": {
        "text": "Single verbatim sentence most similar to the query.",
        "start_offset": 42,
        "end_offset": 93
      },
      "passages": [
        { "text": "...", "start_offset": 42, "end_offset": 93, "score": 0.87 }
      ],
      "chunks": [
        { "text": "...", "score": 0.8700 }
      ]
    }
  ]
}
```

`attachment_url` is `null` when absent, or a URL/path string otherwise. Accepted forms: `http(s)://` external URLs, `/download/`-prefixed paths (built-in ingested articles), and `/uploads/`-prefixed paths (PDFs uploaded via the Upload PDF tab). `attachment_url_type` is `"local"` for `/download/`-prefixed paths or `"external"` for `http(s)://` URLs (also `null` when `attachment_url` is absent). Results where `attachment_url` is null do not render a link in the UI. `best_passage` is the highest-scoring passage from the article (cosine similarity against the query vector). `start_offset` / `end_offset` are character indices into the full article text. `passages` is an array of the top-scoring deduplicated chunk passages for the article, each with the same shape as `best_passage` plus a `score` field; `passages[0]` always equals `best_passage`. `chunks` is an array of all matched chunks for the article, each with a `text` field (the raw chunk text) and a `score` field (cosine similarity, 4 decimal places). Per-passage scores are rendered in the UI as a percentage label (e.g. "· 87%") next to each passage heading.

`POST /articles` accepts either `application/x-www-form-urlencoded` (existing form) or `Content-Type: application/json` with a body of `{ "headline": "...", "details": "...", "attachment_url": "..." }`. Malformed JSON returns HTTP 400; missing required fields return HTTP 422.

`/download/:articleId` validates the `articleId` path parameter — only alphanumeric characters, `-`, and `_` are accepted. Invalid IDs return HTTP 400 "Invalid article ID" before any storage lookup. When the article is not found the response is HTTP 404 "Attachment not found".

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

## Backends

All CLI commands route through a shared factory (`src/store/factory.js`) that
resolves the active VectorStore from the `DB_BACKEND` environment variable.
Set it once and every command (`init`, `ingest`, `search`, `ping`, `verify`)
uses the same backend automatically.

| `DB_BACKEND` | Description |
|--------------|-------------|
| `mock` | **Default.** File-backed store (`collection.json`). No external services required. Ideal for local development, CI, and offline testing. |
| `milvus` | Live Milvus instance. Requires `MILVUS_HOST` (or `docker compose up`). Provides HNSW ANN search with COSINE similarity. |
| `postgres` | Postgres-backed store via pgvector. Requires `DATABASE_URL` (e.g. `postgresql://vectoruser:vectorpass@localhost:5432/vectordb`) and optionally `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` for the pg client. Run `docker compose up postgres` to start the bundled pgvector service. |

Each command prints a startup confirmation line so you always know which backend
is active:

```
[backend] active store: mock
```

### Switching backends

```sh
# Use the file-backed mock (no Docker required):
export DB_BACKEND=mock
node dist/cli.js init
node dist/cli.js ingest

# Use a live Milvus instance:
export DB_BACKEND=milvus
export MILVUS_HOST=localhost    # or your Milvus host
npm run milvus:up               # start docker-compose Milvus
node dist/cli.js init
node dist/cli.js ingest
node dist/cli.js search "your query"
```

Setting `DB_BACKEND` to an unrecognised value causes every command to exit
immediately with a clear error message that includes the invalid value.

## Configuration

Copy `.env.example` to `.env`.

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_BACKEND` | `mock` | Active VectorStore backend (`mock`, `milvus`, `postgres`). Overrides `DATA_BACKEND`. |
| `PORT` | `8000` | Server port (override — see Setup note about 7000/8000) |
| `MILVUS_HOST` | (unset) | Milvus host — when set alongside `DB_BACKEND=milvus`, routes storage and search to Milvus |
| `MILVUS_PORT` | `19530` | Milvus gRPC port |
| `MILVUS_ADDRESS` | `localhost:19530` | Fallback gRPC address for `ping` and the schema helpers when `MILVUS_HOST`/`MILVUS_PORT` are unset |
| `COLLECTION_NAME` | `documents` | Milvus collection name |
| `EMBEDDING_MODEL` | `Xenova/multilingual-e5-small` | Embedding model used by `ingest` and `re-embed`. The first ingest run downloads ~90 MB from HuggingFace; subsequent runs use the cached model. Supports Thai and other scripts via the e5 instruction format (`passage:` / `query:` prefixes). |
| `DIM` | `384` | Embedding dimension — must match the model output (384 for multilingual-e5-small). A mismatch raises a clear error at ingest time. |

## Architecture (current path)

```
src/data/generator.js   built-in 7-doc corpus (6 English + 1 Thai)
  -> src/data/chunker.js         character-window chunks (500 chars / 100 overlap)
  -> src/data/embedder.js        384-dim multilingual-e5-small vectors (via src/embeddings/index.js)
                                 each chunk prefixed "passage: " per e5 instruction format
  -> src/data/collection.js  ->  Milvus (when MILVUS_HOST is set)
                             ->  collection.json (local fallback without Milvus)
  -> attachments/*.txt            downloadable source files

src/commands/re-embed.js  recompute embeddings in-place (mock and postgres backends)

src/core/search.js   embeds query with "query: " e5 prefix, queries Milvus (HNSW COSINE ANN)
                     or falls back to linear cosine scan over collection.json
                     returns passages (with scores) and chunks per result
src/milvus/client.js   singleton MilvusClient wrapper (dynamic SDK import)
src/milvus/schema.ts   Milvus collection schema: HNSW index, COSINE metric, dim=384
src/server.mjs       HTTP: /health, /search, /download, /articles CRUD,
                          /api/upload-pdf (PDF→article JSON), /uploads/ (static PDFs)
src/pdf/index.js     PDF text extraction (embedded text layer → OCR fallback)
src/pdf/mapper.js    Map extracted text to add-article JSON shape
src/ocr/index.js     Ocr interface + TesseractOcr (Thai language, sharp preprocessing)
```
