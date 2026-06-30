# Changelog

Per-sprint changelog for vector-search-demo. Entries are written by the documentor when a
sprint finishes. Dated per-sprint files live under [docs/changelog/](docs/changelog/).

## Sprint 16 (2026-06-30)

- #185: Support multi-model chunk embeddings for corpus comparison (new `chunk_embeddings` table / `chunk_embeddings.json`, `embed-corpus --model <name>` command, and `search --model <name>` flag)
- #187: Improve multi-term keyword matching and proximity ranking (OR-`tsquery` with `ts_rank_cd`, phrase-adjacency boost, and Thai word segmentation via `Intl.Segmenter`)
- #188: Highlight matched query terms in keyword and hybrid results (`<mark>` term highlighting and best-passage-by-term-count selection for lexical modes)

## Sprint 15 (2026-06-26)

- #108: Make re-embed completion message use dynamic model name instead of hardcoded string
- #109: Deduplicate overlapping static assertions from two #98 test files into conftest.py
- #118: Fix _searchMilvus to group chunk hits by parent article (matches file/postgres behaviour)
- #119: Fix Milvus search path to apply MIN_SCORE_THRESHOLD instead of bare score>0 filter
- #121: Add character-count sub-window fallback in splitIntoSentences() for Thai text
- #143: Add range validation for topK (1–500) and hybridFusionWeight (0.0–1.0) in resolveRetrievalConfig — returns HTTP 400 on violation
- #144: Add regression tests anchoring hybrid pipeline / debug-flag decoupling behaviour
- #145: Surface infrastructure errors in run_eval.py — warns to stderr per failed query, exits 1 when all queries fail
- #146: Fix Python eval default port from 7070 to 8000 in run_eval.py and run_ablation.py
- #147: Add stub comment to lexical latency line in searchDocuments clarifying 0ms is not real BM25 cost

## Sprint 14 (2026-06-25)

- #59: Extract shared avgEmbeddings/collapseToArticles to src/store/embedUtils.js (single source of truth)
- #60: Update DESIGN.md postgres backend status from "not yet wired" to fully implemented
- #61: Consolidate Postgres connection config — pg_client.js now prefers DATABASE_URL; PgVectorStore gains checkHealth()
- #71: Fix silent image-fragment loss in _ocrPage — composite all fragments instead of discarding smaller ones
- #73: Call pdfProxy.destroy() after PDF text extraction to prevent WASM/worker resource leak
- #85: Move sharp from dependencies to devDependencies (not required at runtime)
- #86: Remove dead validateArticleId import from server.mjs
- #87: Make PUT /articles/:id non-destructive — embed new chunks before deleting old ones
- #88: Add migration 006 enforcing NOT NULL on article_id and chunk_index columns
- #90: Remove duplicate test file test_canvas_optional_deps__74.py
- #107: Fix reEmbedPostgres row mapping to preserve article_id and chunk_index in upsert payload

## Sprint 13.1 (2026-06-25)

- #140: Add Thai word-boundary chunking mode behind config flag

## Sprint 13 (2026-06-25)

- #135: Add trigram-based lexical search for Thai text
- #136: Add hybrid dense + lexical retrieval with RRF fusion
- #138: Wire reranker into search pipeline behind rerank flag
- #139: Add Thai text normalization at ingest and query time
- #141: Support selectable larger embedding models via config

## Sprint 12 (2026-06-24)

- #130: Add configurable, per-request retrieval pipeline with presets
- #131: Add debug explain mode to search API
- #132: Expand Thai eval set and add nDCG and MRR metrics
- #133: Add ablation runner for comparing retrieval presets
- #134: Upgrade Compare Tab into Configuration Audit Tool

## Sprint 11 (2026-06-20)

- #102: Chunk documents into overlapping vectors for semantic search (chunk defaults: 400 chars / 80 overlap; CHUNK_SIZE/CHUNK_OVERLAP env var overrides; listChunks API on all backends)
- #103: Refactor search to query chunks and group by article (new src/search/index.js; groups chunk hits by article_id; SEARCH_MAX_CHUNKS cap; /search accepts n param)
- #104: Show multiple matching passages per search result card (Passage TypeScript type with context.before/after; passages array in SearchResult; per-chunk scores in UI)
- #105: Add rechunk command and chunk integrity verification (rechunk CLI command deletes and regenerates all chunks; verify checks ≥1 chunk per article and non-null embeddings)

## Sprint 10 (2026-06-20)

- #97: Switch embedder to multilingual-e5-small for Thai support
- #98: Chunk documents into overlapping character-window segments before indexing
- #99: Group multi-chunk search results by parent document (adds `chunks` field)
- #100: Show multiple matching passages per result card with per-passage scores

## Sprint 8 (2026-06-19)

- #41: Clarify articleId validation return semantics via getArticleIdError alias
- #42: Add docstring to resolveAttachmentUrlType helper
- #74: Move @napi-rs/canvas to optionalDependencies
- #80: Store and retrieve Postgres embeddings at chunk granularity
- #81: Return and render multiple passages per search result
- #82: Add exact-keyword search endpoint (GET /search/exact) and Compare tab

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
