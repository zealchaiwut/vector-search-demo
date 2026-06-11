# vector-search-demo

A semantic document-search demo: a `commander` CLI plus a Fastify web server that
ingests documents, ranks them by similarity to a query, and serves the source files
for download. Includes a recall@k evaluation harness.

> **Status: working demo on a mock backend.** Search runs end-to-end, but the
> ranking is **TF-IDF cosine over a local JSON file** — **not** Milvus and **not**
> neural embeddings. See [What's built / not built](#whats-built--not-built).

## What's built / not built

### ✅ Built and verified end-to-end
- **CLI** (`init`, `ingest`, `search`, `serve`, `ping`) via `node dist/cli.js <cmd>`.
- **Ingestion pipeline** — a small built-in corpus (6 docs in `src/data/generator.js`)
  is chunked, embedded (TF-IDF), written to a file-backed collection
  (`collection.json`), and saved as downloadable `.txt` files under `attachments/`.
- **Search** — `core/search.js` reads the ingested `collection.json`, builds a TF-IDF
  space over the chunks, and ranks documents by cosine similarity (over-fetch + collapse
  per document).
- **HTTP API** — one Fastify server with `/health`, `/search`, `/download/:docId`
  (GET + HEAD), and the search UI at `/`.
- **Evaluation** — `npm run eval` reports recall@k against the running server.
  Current corpus + fixtures score **recall@5 = 1.00**.

### ❌ Not built / not wired (despite being present in the tree)
- **Milvus is NOT used by search or ingest.** The container runs and `ping` talks to it,
  but `milvus/schema.js` and `milvus/client.js` are otherwise unused. Storage is a plain
  JSON file, scanned linearly.
- **Neural embeddings are NOT used.** `embeddings/index.js` (Transformers.js / MiniLM,
  384-dim) is imported nowhere. Ranking is keyword-frequency TF-IDF, not learned vectors.
  No model download happens.
- **No real ANN index** (no HNSW/IVF) — the `dim`, `EMBEDDING_MODEL`, etc. config keys
  are vestigial for the current path.
- **Corpus is a fixed built-in set**, not loaded from external files or a real data source.

Wiring the genuine path (MiniLM embeddings → Milvus via gRPC) is the next step and is
not done.

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

Copy `.env.example` to `.env`. Only `PORT` affects the current (file-backed) path;
the Milvus/embedding keys are read but unused until the real backend is wired.

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `8000` | Server port (override — see Setup note about 7000/8000) |
| `MILVUS_ADDRESS` | `localhost:19530` | Milvus gRPC address (used only by `ping`; `MILVUS_HOST`/`MILVUS_PORT` override it when set) |
| `COLLECTION_NAME` | `documents` | Collection name (unused by file backend) |
| `EMBEDDING_MODEL` | `Xenova/all-MiniLM-L6-v2` | Embedding model (not yet wired) |
| `DIM` | `384` | Embedding dimension (not yet wired) |

## Architecture (current path)

```
src/data/generator.js   built-in 6-doc corpus
  -> src/data/chunker.js     split into chunks
  -> src/data/embedder.js    TF-IDF vectors
  -> src/data/collection.js  -> collection.json   (file-backed "collection")
  -> attachments/*.txt        downloadable source files

src/core/search.js   reads collection.json, TF-IDF cosine ranking
src/server/index.ts  Fastify: /health, /search, /download, /

Unwired (real backend): src/milvus/*, src/embeddings/*
```
