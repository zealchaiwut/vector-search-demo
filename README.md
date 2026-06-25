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
  `src/data/generator.js`) is chunked into overlapping 400-character windows (80-char
  overlap, character-based for Thai compatibility), embedded using multilingual-e5-small
  (384-dim, `src/embeddings/index.js`), stored in Milvus (`MILVUS_HOST` set) or a local
  `collection.json` fallback, and saved as downloadable `.txt` files under `attachments/`.
  Chunk size and overlap are configurable via `CHUNK_SIZE` and `CHUNK_OVERLAP` env vars.
- **Search** — `search/index.js` embeds the query with the `query:` e5 instruction prefix and
  runs ANN search via Milvus (HNSW COSINE, EF=64 over-fetch, chunk collapsing per article)
  when `MILVUS_HOST` is set, or falls back to a linear cosine scan over `collection.json`.
  Each result includes a `passages` array (top-scoring deduplicated chunks with per-chunk
  scores) and a `chunks` array (all matched chunks for the article, each with `text` and
  `score`) in addition to `best_passage`. The number of chunk hits surfaced per article is
  capped by `SEARCH_MAX_CHUNKS` (default 3) or the `n` query parameter on `/search`.
- **Exact/keyword search** — `GET /search/exact` runs Postgres FTS (`plainto_tsquery` +
  `ts_rank` over a GIN-indexed `tsvector` column). Only active when `DB_BACKEND=postgres`.
- **Configuration Audit Tool (Compare tab)** — the search UI has a side-by-side tab
  with two preset selector dropdowns (Preset A / Preset B). Submitting a query fires
  parallel requests under each preset with explain mode enabled; each result card shows
  per-stage scores (dense, sparse, rerank) so ranking differences are immediately visible.
  Changing a preset reruns only that column without a page reload.
- **Configurable retrieval pipeline** — `src/config/retrieval.js` defines a `RetrievalConfig`
  covering embedding model, top-k, hybrid fusion, reranking, chunking, and text
  normalisation. Resolution order: env-var defaults → named preset → per-request overrides.
  Built-in named presets: `dense-only`, `hybrid`, `hybrid-rerank`. Invalid preset names
  return HTTP 400.
- **Debug explain mode** — add `debug=true` to any search request to attach an `explain`
  block to each result showing per-stage score, rank, rank delta, and latency (ms). Stages
  that did not run are omitted entirely. No overhead is incurred on non-debug requests.
- **Chunk-granularity Postgres storage** — the Postgres backend (`DB_BACKEND=postgres`)
  stores one row per chunk (sharing `article_id`), with a generated `tsvector` column for
  full-text search (migration `003_tsvector.sql`).
- **HTTP API** — one Fastify server with `/health`, `/search`, `/download/:docId`
  (GET + HEAD), and the search UI at `/`.
- **Evaluation** — `npm run eval` (JS, fixed fixtures) reports recall@k against the
  running server. `python3 src/eval/run_eval.py` runs the Thai eval set and reports
  Recall@k, nDCG, and MRR. `python3 src/eval/run_ablation.py` compares presets
  side-by-side in a metrics table (Recall@k, nDCG, MRR, avg latency).

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
node dist/cli.js verify               # check every article has ≥1 chunk and every chunk has a non-null embedding
node dist/cli.js re-embed             # recompute embeddings for all existing articles/chunks
node dist/cli.js rechunk              # delete and regenerate all chunks using current CHUNK_SIZE/CHUNK_OVERLAP settings, then re-embed
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
| `GET` | `/api/config` | Runtime config for the UI (`{ "env": "prd" }` from `ENV` in `.env`) |
| `GET` | `/api/presets` | List available named retrieval presets (`{ "presets": ["dense-only", "hybrid", "hybrid-rerank"] }`) |
| `GET` | `/search?q=<query>[&preset=<name>][&debug=true][&topK=N][&rerankEnabled=true\|false][&k=<n>][&n=<chunks>]` | Return top-k ranked result cards (semantic). `preset` selects a named config; additional params override individual fields. `n` caps chunk hits per article. `debug=true` adds per-result `explain` blocks. |
| `POST` | `/search` | Same as `GET /search` but accepts JSON body `{ "q": "...", "preset": "...", "debug": true, ...overrides }`. |
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
      ],
      "explain": [
        { "stage": "dense",  "score": 0.87, "rank": 1, "rankDelta": 0,  "latencyMs": 12.4 },
        { "stage": "rerank", "score": 0.91, "rank": 1, "rankDelta": 0,  "latencyMs": 8.1 }
      ]
    }
  ],
  "config": {
    "embeddingModelId": "Xenova/all-MiniLM-L6-v2",
    "topK": 10,
    "hybridEnabled": false,
    "hybridFusionWeight": 0.7,
    "rerankEnabled": false,
    "rerankModelId": "cross-encoder/ms-marco-MiniLM-L-6-v2",
    "chunkSize": 400,
    "chunkOverlap": 80,
    "textNormalisationEnabled": true
  },
  "activePreset": "hybrid-rerank"
}
```

`explain` is only present on each result when `debug=true`. Stages that did not run are omitted (never null). `config` is always returned and reflects the resolved `RetrievalConfig` for the request. `activePreset` is only present at the top level when `debug=true`.

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

### Thai eval runner (`src/eval/run_eval.py`)

Runs the labeled Thai query set (`src/eval/thai_eval_set.json`) and reports
**Recall@k**, **nDCG@k**, and **MRR** against the running server.

```sh
python3 src/eval/run_eval.py
```

| Env var | Default | Description |
|---------|---------|-------------|
| `SEARCH_URL` | `http://localhost:7070/search` | Search endpoint |
| `K` | `10` | Top-k for all three metrics |
| `RECALL_THRESHOLD` | `0.80` | Minimum recall@k to pass |
| `EVAL_DATASET` | `src/eval/thai_eval_set.json` | Path to labeled dataset |
| `COLLECTION_FILE` | (unset) | Optional corpus JSON for ID validation |

Exit code 0 when recall@k ≥ threshold; non-zero with a descriptive error if any
expected ID is absent from the corpus.

### Ablation runner (`src/eval/run_ablation.py`)

Compares multiple named presets side-by-side in one run, printing Recall@k, nDCG,
MRR, and avg query latency per preset.

```sh
python3 src/eval/run_ablation.py [--config src/eval/ablation_presets.json] [--output results.json]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--config FILE` | `src/eval/ablation_presets.json` | YAML or JSON preset definitions |
| `--output FILE` | (none) | Write results to JSON or CSV (includes timestamp) |
| `--search-url URL` | `http://localhost:7070/search` | Search endpoint |
| `--k N` | `10` | Top-k for all metrics |
| `--dataset FILE` | `src/eval/thai_eval_set.json` | Labeled dataset |

Adding a new preset requires only editing the config file — no code changes. If one
preset fails, the runner reports the error and continues with the remaining presets.

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
| `ENV` | `local` | Deployment label in the UI header. Set to `prd` or `uat` to show `[PRD]` / `[UAT]`; `local` hides the badge. |
| `DB_BACKEND` | `mock` | Active VectorStore backend (`mock`, `milvus`, `postgres`). Overrides `DATA_BACKEND`. |
| `PORT` | `8000` | Server port (override — see Setup note about 7000/8000) |
| `MILVUS_HOST` | (unset) | Milvus host — when set alongside `DB_BACKEND=milvus`, routes storage and search to Milvus |
| `MILVUS_PORT` | `19530` | Milvus gRPC port |
| `MILVUS_ADDRESS` | `localhost:19530` | Fallback gRPC address for `ping` and the schema helpers when `MILVUS_HOST`/`MILVUS_PORT` are unset |
| `COLLECTION_NAME` | `documents` | Milvus collection name |
| `EMBEDDING_MODEL` | `Xenova/multilingual-e5-small` | Embedding model used by `ingest` and `re-embed`. The first ingest run downloads ~90 MB from HuggingFace; subsequent runs use the cached model. Supports Thai and other scripts via the e5 instruction format (`passage:` / `query:` prefixes). |
| `DIM` | `384` | Embedding dimension — must match the model output (384 for multilingual-e5-small). A mismatch raises a clear error at ingest time. |
| `CHUNK_SIZE` | `400` | Characters per chunk used by `ingest` and `rechunk`. Character-based (not whitespace), so Thai text is handled correctly. |
| `CHUNK_OVERLAP` | `80` | Character overlap between consecutive chunks for `ingest` and `rechunk`. |
| `SEARCH_MAX_CHUNKS` | `3` | Maximum number of chunk hits to surface per article in search results. Can also be overridden per-request with the `n` query parameter on `GET /search`. |
| `RETRIEVAL_EMBEDDING_MODEL_ID` | `Xenova/all-MiniLM-L6-v2` | Default embedding model for the retrieval pipeline. |
| `RETRIEVAL_TOP_K` | `10` | Default number of results returned by the search endpoint. |
| `RETRIEVAL_HYBRID_ENABLED` | `false` | Enable hybrid dense+sparse (BM25) fusion by default. |
| `RETRIEVAL_HYBRID_FUSION_WEIGHT` | `0.7` | Dense/sparse blend weight (0–1, higher = more dense). |
| `RETRIEVAL_RERANK_ENABLED` | `false` | Enable cross-encoder reranking by default. |
| `RETRIEVAL_RERANK_MODEL_ID` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Cross-encoder model used for reranking. |
| `RETRIEVAL_CHUNK_SIZE` | `400` | Per-request chunk size default (falls back to `CHUNK_SIZE`). |
| `RETRIEVAL_CHUNK_OVERLAP` | `80` | Per-request chunk overlap default (falls back to `CHUNK_OVERLAP`). |
| `RETRIEVAL_TEXT_NORMALISATION_ENABLED` | `true` | Normalise text before embedding by default. |

## Architecture (current path)

```
src/data/generator.js   built-in 7-doc corpus (6 English + 1 Thai)
  -> src/data/chunker.js         character-window chunks (400 chars / 80 overlap; override
                                 via CHUNK_SIZE and CHUNK_OVERLAP env vars)
  -> src/data/embedder.js        384-dim multilingual-e5-small vectors (via src/embeddings/index.js)
                                 each chunk prefixed "passage: " per e5 instruction format
  -> src/data/collection.js  ->  Milvus (when MILVUS_HOST is set)
                             ->  collection.json (local fallback without Milvus)
  -> attachments/*.txt            downloadable source files

src/commands/re-embed.js  recompute embeddings in-place (mock and postgres backends)
src/commands/rechunk.js   delete all existing chunks for each article, re-chunk with current
                          settings, re-embed, and re-store (mock and postgres backends)
src/commands/verify.js    integrity check: every article has ≥1 chunk, every chunk has a
                          non-null embedding; exits 0 on pass, 1 on failure

src/config/retrieval.js  RetrievalConfig: env-var defaults, named presets (dense-only,
                         hybrid, hybrid-rerank), per-request override parsing and resolution
src/search/index.js  embeds query with "query: " e5 prefix, queries Milvus (HNSW COSINE ANN)
                     or Postgres (pgvector cosine) or falls back to linear cosine scan over
                     collection.json; groups chunk hits by article_id (capped at
                     SEARCH_MAX_CHUNKS per article); returns passages and chunks per result;
                     optional debug explain trail (per-stage score/rank/latency) per result
src/milvus/client.js   singleton MilvusClient wrapper (dynamic SDK import)
src/milvus/schema.ts   Milvus collection schema: HNSW index, COSINE metric, dim=384
src/server.mjs       HTTP: /health, /search (GET+POST, preset/config overrides, debug mode),
                          /api/presets, /download, /articles CRUD,
                          /api/upload-pdf (PDF→article JSON), /uploads/ (static PDFs)
src/eval/run_eval.py     Thai eval: Recall@k, nDCG, MRR against thai_eval_set.json
src/eval/run_ablation.py Ablation runner: side-by-side preset comparison table
src/eval/thai_eval_set.json Labeled Thai query → expected article IDs dataset
src/eval/ablation_presets.json Default preset list for the ablation runner
src/pdf/index.js     PDF text extraction (embedded text layer → OCR fallback)
src/pdf/mapper.js    Map extracted text to add-article JSON shape
src/ocr/index.js     Ocr interface + TesseractOcr (Thai language, sharp preprocessing)
```
