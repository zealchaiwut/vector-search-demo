# vector-search-demo — chunk-level retrieval + search comparison

**Date:** 2026-06-19
**Sprint label:** sprint-8
**Default labels:** enhancement
**Status:** drafted

## Context

Project: **vector-search-demo** (TS/Node, Postgres/pgvector backend, web UI at
`public/index.html` served by `src/server.mjs`).

Current retrieval is coarse because of two coupled limitations found while debugging the
PDF/Postgres deploy:

1. The Postgres store **collapses and averages all chunks into one row + one averaged
   embedding per article** (`collapseToArticles` → `avgEmbeddings` in
   `src/data/collection.js`). The demo corpus *is* chunked at ingest
   (`src/data/chunker.js`, 120-word windows / 30 overlap) but Postgres averages it away.
   PDF/Add/Bulk articles are stored as a single `:0` chunk (whole body → one embedding).
2. `selectBestPassage()` in `src/core/search.js` returns a **single** best sentence
   (+2 context sentences). Multi-keyword queries that hit several distinct sentences still
   surface only one passage.

This batch makes retrieval chunk-granular (so a long doc can match in multiple places),
surfaces multiple passages per result, and adds an exact-keyword search mode for
side-by-side comparison with semantic search. Ticket B depends on Ticket A.

Search already has a working Postgres path (`_searchPostgres`) and the web server is wired
to Postgres via `data/collection.js`. The `articles` table is defined in
`src/store/migrations/001_articles.sql`.

## Prompts

Paste one code block into the Bulk Create textarea. Prompts are `---`-separated.

```
Make Postgres retrieval chunk-granular instead of one averaged vector per article. Today src/data/collection.js collapses chunk rows into one row per article and averages their embeddings (collapseToArticles/avgEmbeddings), and src/server.mjs stores user/PDF/bulk articles as a single ":0" chunk. Change the Postgres store + schema so each chunk is its own row with its own embedding: store id like "<articleId>:<n>", keep PK on the full chunk id, add the article_id and chunk_index columns (migration must be idempotent and additive). Stop averaging on upsert — persist each chunk row as-is. Update PgVectorStore.upsert/list/get/delete/count and the data/collection.js postgres branch so: listArticles() collapses chunk rows back to one entry per article (dedupe by article_id, join nothing — return headline/attachment_url + the article-level details), getArticle(id) returns the article (all chunks joined in chunk order), deleteArticle(id) deletes all chunks for that article (by article_id prefix), entityCount() counts articles (distinct article_id) while a separate chunk count is available for integrity. Server-side, chunk articles on create/update/bulk and on PDF import using the existing src/data/chunker.js before embedding+upsert. Acceptance: ingesting the demo corpus yields multiple chunk rows per article in Postgres (no averaged single row); creating an article with a long body stores multiple chunk rows; GET /articles lists one entry per article; GET /articles/:id returns the full joined body; DELETE removes all chunks; /health/integrity reports article vs chunk counts without false mismatch; existing pg tests pass or are updated; npm run typecheck clean.
---
Return and render multiple matching passages per search result (depends on the chunk-level retrieval ticket). With chunk-granular search, a query can match several chunks of the same article. Update src/core/search.js so the Postgres search path groups chunk hits by article_id, keeps the top matching chunks per article (cap at e.g. 3, above a small score threshold), and for each returned article includes an array of passages — each passage is the best sentence within a matched chunk with the same {text, start_offset, end_offset, context:{before,after}} shape selectBestPassage already produces, plus the chunk's own score. Keep the single best_passage field for backward compatibility (highest-scoring passage). Update public/index.html result rendering to show all passages for a result (stacked, each with the existing highlight styling) instead of only one, with the highest-scoring one first. Acceptance: a multi-keyword query against a long article returns multiple distinct passages from different parts of the document; the UI renders each highlighted passage in order; results that match in one place still show exactly one; best_passage remains populated; no duplicate/overlapping passages from overlapping chunks (dedupe by sentence offset); npm run typecheck clean.
---
Add an exact-keyword search mode as a separate comparison screen alongside semantic search. Add a lexical search path that ranks by exact keyword/term matching using Postgres full-text search (to_tsvector/plainto_tsquery + ts_rank) over headline+details; expose it as GET /search/exact?q=&k= returning the same result card shape as /search (id, headline, details, score, attachment_url, best_passage where the passage is the matched-term snippet via ts_headline or a term-window). Add a new "Compare" tab (or a toggle on the search screen) in public/index.html that runs the query against both /search (semantic) and /search/exact (keyword) and shows the two ranked lists side by side so the difference is visible, with exact-term highlighting on the keyword side. Document the migration if a tsvector column/GIN index is added (idempotent migration). Acceptance: GET /search/exact returns keyword-ranked results and an empty array for no lexical match; the Compare screen shows semantic vs exact results side by side for the same query; exact side highlights the literal query terms; a query with a rare exact term ranks the exactly-matching doc first on the keyword side but not necessarily on the semantic side (demonstrating the difference); existing /search behavior unchanged; npm run typecheck clean.
```

## Notes

- **Dependency:** Ticket 2 (multi-passage rendering) depends on Ticket 1 (chunk-level
  retrieval) — schedule/merge Ticket 1 first. Ticket 3 (exact-keyword compare) is
  independent and can run in parallel.
- **Migrations** must be idempotent and additive (the live UAT deploy runs
  `cli.js init` on start via `scripts/deploy-start.sh`). Don't drop/rename existing
  columns; add new ones (`article_id`, `chunk_index`, optional `tsv`).
- Backends other than Postgres (mock/milvus) should keep working — the mock path already
  stores per-chunk rows and collapses on read, so mirror that behavior for Postgres.
- Touch points: `src/data/collection.js`, `src/store/PgVectorStore.js`,
  `src/store/postgres.js`, `src/store/migrations/`, `src/core/search.js`,
  `src/server.mjs`, `public/index.html`, `src/data/chunker.js` (reuse, don't rewrite).
- Already shipped separately (not in this batch): full-article modal for imported
  articles (PR #78), PDF upload progress bar + no-cache (PR #77), Postgres deploy wiring
  (PR #76).

## Posted issues

| # | Title | Size |
|---|-------|------|
| _pending_ | | |
