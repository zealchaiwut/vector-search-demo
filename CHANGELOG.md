# Changelog

Per-sprint changelog for vector-search-demo. Entries are written by the documentor when a
sprint finishes. Dated per-sprint files live under [docs/changelog/](docs/changelog/).

## Sprint 7 (2026-06-19)

- #66: Add PDF text extraction service with Thai OCR
- #67: Map extracted PDF text to add-article JSON shape
- #68: Add JSON body support to article create endpoint and form
- #69: Add Upload PDF Tab with Extraction and Article Creation

## Sprint 6.1 (2026-06-19)

- #50: Add Postgres + pgvector backend alongside Milvus
- #51: Add Postgres pgvector backend to VectorStore
- #52: Route all commands through DB_BACKEND factory with docs and parity test

## Sprint 5 (2026-06-11)

- #24: Clarify scope path for best_passage implementation (src/search vs src/core)
- #27: Clarify attachment URL resolution semantics in search results
- #28: Update /download error message to mention attachments
- #38: Validate or parameterize articleId in Milvus filter expressions to prevent injection

## Sprint 4 (2026-06-11)

- #30: Wire init and ingest commands to real Milvus collection
- #31: Replace TF-IDF embedder with MiniLM in ingest
- #32: Wire search to real Milvus vector search
- #33: Port article CRUD operations from file to Milvus
- #34: Wire article upload form to Milvus collection

## Sprint 3.1 (2026-06-11)

- #20: Add input validation and vector-article integrity check
- #21: Replace Download button with external attachment link

## Sprint 2.1 (2026-06-10)

- #13: Rebuild search results page to approved mock
- #14: Add best-matching passage to search results

## Sprint 1.2 (2026-06-10)

- #1: Scaffold TypeScript monolith with CLI and Fastify server
- #2: Add Milvus standalone setup and ping command
- #3: Define Milvus collection schema and vector index
- #4: Implement Transformers.js embedding module with MiniLM
- #5: Build ingestion pipeline for commander ingest command
- #6: Add search core and HTTP API endpoints
- #7: Wire CLI search command to searchDocuments core
- #8: Wire search UI to /search endpoint with result cards
- #9: Add recall@k evaluation script for search quality
