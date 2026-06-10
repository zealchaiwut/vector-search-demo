# vector-search-demo

End-to-end semantic vector search demo: embed, index, query, and evaluate search quality.

## Prerequisites

- Node.js >= 18
- Docker (for Milvus)

## Setup

```sh
npm install
cp .env.example .env
npm run milvus:up   # start Milvus via Docker Compose
```

## CLI commands

```sh
# Start the HTTP server (default port 3000)
node dist/cli.js serve
# or in dev mode:
npm run dev

# Check Milvus connectivity
node dist/cli.js ping

# Ingest documents into Milvus
node dist/cli.js ingest

# Search indexed documents
node dist/cli.js search <query terms>
```

## npm scripts

| Script | Description |
|--------|-------------|
| `npm run build` | Compile TypeScript to `dist/` |
| `npm run dev` | Run server in watch mode (tsx) |
| `npm start` | Start compiled server |
| `npm run eval` | Run recall@k evaluation script |
| `npm run milvus:up` | Start Milvus via Docker Compose |
| `npm run milvus:down` | Stop Milvus |

## HTTP API

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Serve search UI (`public/index.html`) |
| `GET` | `/search?q=<query>&k=<n>` | Return top-k ranked result cards |
| `GET` | `/download/:docId` | Download source document as `.txt` |

Result shape:

```json
{
  "results": [
    { "doc_id": "...", "title": "...", "snippet": "...", "score": 0.95, "attachment_name": "...", "download_url": "..." }
  ]
}
```

## Evaluation

Run `npm run eval` to execute the recall@k evaluation script against the running server.

| Env var | Default | Description |
|---------|---------|-------------|
| `SEARCH_URL` | `http://localhost:3000/search` | Search API endpoint |
| `K` | `5` | Number of top results to check |
| `RECALL_THRESHOLD` | `0.8` | Minimum pass fraction (0.0–1.0) |

Exit code 0 when recall@k ≥ threshold.

## Configuration

Copy `.env.example` to `.env` and set:

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `8000` | Server port |
| `MILVUS_ADDRESS` | `localhost:19530` | Milvus gRPC address |
| `COLLECTION_NAME` | `documents` | Milvus collection name |
| `EMBEDDING_MODEL` | `Xenova/all-MiniLM-L6-v2` | Embedding model |
| `DIM` | `384` | Embedding dimension |
