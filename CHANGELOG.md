# Changelog

Per-sprint changelog for vector-search-demo. Entries are written by the documentor when a
sprint finishes. Dated per-sprint files live under [docs/changelog/](docs/changelog/).

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
