# vector-search-demo — make retrieval real (per-model index, Thai FTS, reranker)

**Date:** 2026-06-29
**Sprint label:** sprint-9
**Default labels:** enhancement
**Status:** drafted

## Context

Project: **vector-search-demo** (TS/Node, Postgres/pgvector backend, web UI at
`public/index.html` served by `src/server.mjs`; search pipeline in `src/search/`,
embeddings in `src/embeddings/`, lexical FTS in `src/core/lexical/`).

Three UAT findings from the Search/Compare tabs are structural, not cosmetic
(the highlight-only fixes already shipped). Each needs a re-index, so they belong
together:

1. **Model dropdown does nothing.** `createEmbedder()` (`src/embeddings/index.js`)
   is a module-level singleton bound to one env model (`EMBEDDING_MODEL`) and
   ignores any per-call model. Chunks are indexed with a single model's vectors,
   so the Compare tab shows identical dense scores for BGE-M3 vs E5, and the
   Search tab has no model selector because it would be a no-op.
2. **Thai keyword search doesn't match.** The `articles` table has only the
   `english` `ts` column. Postgres `english`/`simple` configs tokenise on
   whitespace, and Thai compounds have no internal spaces, so `ปัญหาทุจริต`
   never matches `ทุจริต` in a document. (Highlighting of Thai terms is already
   fixed via Intl.Segmenter on the client.)
3. **Relevance is stuck ~20% (uniform).** The cross-encoder ONNX reranker
   (`src/rerank/BgeRerankerV2M3.js`) isn't loading, so it falls back to the weak
   n-gram sidecar that returns near-uniform low scores.

Related shipped work: chunk-level retrieval + multi-passage (sprint-8), chunk cap
+ bounded/monotonic relevance + Thai highlight (PRs #182/#183/#195).

## Prompts

Paste one code block into the Bulk Create textarea. Prompts are `---`-separated.

```
Make the embedding model actually selectable by indexing per-model vectors. Today createEmbedder() in src/embeddings/index.js is a singleton bound to EMBEDDING_MODEL and chunks store one vector, so the Compare/Search model dropdown has no effect (BGE-M3 and E5 return identical dense scores). Refactor createEmbedder(modelId) to build/cache one pipeline per model id (keyed map, not a single _pipe) resolved through model-registry, and thread a modelId through searchDocuments() → _searchPostgres/_searchFile and the query embed call. Store embeddings per model: add a per-model vector column or a chunk_embeddings(article_id, chunk_index, model_id, embedding vector) table (migration must be idempotent/additive; different models have different dims, so key the index by model_id). Update ingest to embed+store for each registered model (or a configured MODELS list). The /search and /compare endpoints read the model param and query the matching column/table; when a doc has no vector for the requested model, it is simply absent from dense results for that model. Acceptance: ingest populates vectors for at least two models (e.g. multilingual-e5 and bge-m3); GET /search?model=<id> returns different dense scores/rankings for the two models on the same query; the Compare tab's two model dropdowns produce genuinely different columns; existing single-model behaviour still works when only one model is configured; migration is idempotent; npm run typecheck clean.
---
Add a model selector to the Search tab and expose the active model in results. The Search tab (public/index.html) has no model picker, unlike Compare. Add a Model dropdown (populated from GET /api/models) next to the Search mode selector; pass the chosen model to /search via a model query param; show the active model id somewhere on the results header. Depends on the per-model indexing ticket (the param must actually switch the vector space). Acceptance: the Search tab shows a Model dropdown listing the canonical models; changing it re-runs the search against that model and yields different rankings; the selected model is visible in the results; defaulting (no selection) matches current behaviour; npm run typecheck clean.
---
Make Thai keyword/full-text search actually match. The articles table only has an 'english' ts column, so Thai compounds (e.g. "ปัญหาทุจริต") never match documents containing "ทุจริต". Segment Thai at ingest and index a segmented tsvector: add a stored column (e.g. ts_simple) built from text that has Thai word breaks inserted (use Intl.Segmenter / an ICU word segmenter at ingest time to space-separate Thai, since Postgres cannot segment Thai itself), and have the lexical scorer in src/core/lexical (tsvectorOrScorer / thaiSegmenter) build to_tsquery('simple', ...) from the segmented query tokens against that column when the query contains Thai. Provide an idempotent, additive migration for the new column/index and a backfill path (re-ingest or an UPDATE that segments existing rows). Acceptance: keyword search for "ปัญหาทุจริต" returns documents that contain "ทุจริต" and/or "ปัญหา"; English keyword search is unchanged; the lexical scorer selects the Thai path only for Thai queries; migration is idempotent and includes a backfill for existing rows; a test covers a Thai compound query matching a segmented document; npm run typecheck clean.
---
Load the real cross-encoder reranker instead of the weak sidecar fallback. Reranking (src/rerank/BgeRerankerV2M3.js) currently falls back to the n-gram sidecar, so Hybrid+Rerank relevance is near-uniform (~20% for every hit). Diagnose why the Transformers.js ONNX pipeline (Xenova/bge-reranker-v2-m3, or cross-encoder/ms-marco-MiniLM-L-6-v2) does not load (missing dependency, model not cached, wrong task/format) and make it load and score by default; keep the sidecar strictly as a last-resort fallback and log which path is active. Ensure the reranker output feeds the existing relevancePct() so scores spread across the range (a strong match ranks clearly above a weak one) rather than clustering at one value. Acceptance: with the real model available, Hybrid+Rerank produces a spread of relevance scores (not all equal) and orders an obviously-relevant doc above an irrelevant one; the active reranker path is logged; the sidecar still works when the model is unavailable; npm run typecheck clean.
```

## Notes

- **Dependencies:** the Search-tab model selector ticket depends on the per-model
  indexing ticket (the param must switch a real vector space). The Thai-FTS and
  reranker tickets are independent and can run in parallel.
- **Re-index required:** per-model indexing and Thai segmentation both change what
  is stored, so the corpus must be re-ingested after they land. Migrations must be
  idempotent + additive (the live UAT deploy runs `cli.js init` on start).
- **Models have different dims** (e5-small 384, bge-m3 1024, e5-large 1024) — a
  per-model vector table keyed by `model_id` avoids a fixed-dim column clash.
- Keep mock/milvus backends working; Postgres is the primary target.

## Posted issues

| # | Title | Size |
|---|-------|------|
| _pending_ | | |
