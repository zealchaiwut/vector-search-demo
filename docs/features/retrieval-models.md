# Retrieval Models — Dense, Hybrid, Hybrid + Rerank

Technical reference for the three retrieval presets exposed by the search UI and
API, how the vector database runs on Postgres (pgvector), how Thai-language text
is handled end to end, and the three ranking-model options the pipeline supports.

- **Code:** `src/search/index.js` (pipeline), `src/config/retrieval.js` (presets),
  `src/store/PgVectorStore.js` (Postgres), `src/core/searchExact.js` (keyword/FTS),
  `src/rerank/` (cross-encoder), `src/embeddings/` (embedders), `src/text/normalise.js` (Thai).
- **API:** `GET /search?q=&preset=<name>&debug=true&k=` and `GET /search/exact?q=&k=`.
- **Presets:** `dense-only`, `hybrid`, `hybrid-rerank` (from `/api/presets`).

---

## 1. The three presets

Config is resolved per request in `resolveRetrievalConfig()`
(`src/config/retrieval.js`), in order: **env-var defaults → named preset →
per-request overrides**. The presets differ only in which pipeline stages are
switched on:

| Preset | `hybridEnabled` | `rerankEnabled` | Stages run | Use for |
|---|---|---|---|---|
| `dense-only` | false | false | dense | Pure semantic; fastest |
| `hybrid` | true | false | dense → lexical → rrf | Meaning **and** exact terms |
| `hybrid-rerank` | true | true | dense → lexical → rrf → rerank | Best quality; slowest (UI default) |

Shared defaults (all three): `topK: 10`, `rrfK: 60`, `hybridFusionWeight: 0.7`,
`rerankCandidateCount: 50`, `chunkSize: 400`, `chunkOverlap: 80`,
`textNormalisationEnabled: true`, `chunkingMode: "length"`.

### Pipeline stages (`src/search/index.js`)

When `debug=true`, each stage emits an **explain score** per result
(`_recordExplainStage`, stage names: `dense`, `lexical`, `rrf`, `rerank`) — these
are the pills shown in the Compare tab.

**Stage 1 — Dense (semantic) retrieval.** The query is normalised and embedded,
then matched by vector similarity:

```js
const retrievalK = cfg.rerankEnabled ? Math.max(topK, rerankCandidateCount) : topK;
const candidates = await store.search(queryEmbedding, EF);
```

When reranking is on, a **larger candidate pool** (`max(topK, 50)`) is pulled so
the cross-encoder has more to re-score. Score = cosine similarity (see §2).

**Stage 2 — Lexical scoring** (hybrid only). A keyword/trigram score is computed
for the same candidates via `searchLexical()` →
`trigramScorer` (`src/core/lexical/trigramScorer.js`), using Postgres
`word_similarity()` (pg_trgm). Trigrams work on raw Unicode, so this path is
script-agnostic (matters for Thai — §3).

**Stage 3 — RRF fusion** (hybrid only). Dense and lexical ranked lists are merged
by **Reciprocal Rank Fusion** (`src/search/rrf.js`):

```text
score = 1/(k + dense_rank) + 1/(k + lexical_rank)        # k = rrfK, default 60
```

RRF combines by **rank position, not raw score**, so the two stages' very
different score scales never have to be normalised. A `null` rank means the doc
was absent from that list (e.g. term omitted). `rrfK` softens how much the very
top ranks dominate; `hybridFusionWeight` (0.7) is the configured dense/lexical
blend knob.

**Stage 4 — Cross-encoder rerank** (hybrid-rerank only). The fused top candidates
are re-scored by a cross-encoder that reads query + passage **together**:

```js
const reranker = createReranker();                 // src/rerank/index.js
const rerankScores = await reranker.rerank(normalisedQuery, chunks);
```

Each result's `score` is replaced by its cross-encoder relevance score and the
list is re-sorted. This is the most accurate stage and the most expensive — it
runs a transformer forward pass per candidate.

---

## 2. Vector DB on Postgres (pgvector)

The data layer is pluggable via `DB_BACKEND` (`src/data/backend.js`):

| `DB_BACKEND` | Store | Notes |
|---|---|---|
| `mock` (default) | file-backed `collection.json` + TF-IDF | No DB needed |
| `postgres` | `PgVectorStore` (pgvector) | Dense + FTS + trigram |
| `milvus` | Milvus store | Separate stack |

Set `DB_BACKEND=postgres` and `DATABASE_URL=postgres://…` to switch from the mock
to real Postgres. `usePostgres()` (`src/data/backend.js:12`) gates the keyword
and dense SQL paths — they return `[]` on non-Postgres backends.

### Schema & extensions

`PgVectorStore` provisions the schema (`src/store/PgVectorStore.js`) plus
idempotent migrations in `src/store/migrations/`:

```sql
CREATE EXTENSION IF NOT EXISTS vector;            -- pgvector (migration 001 / store)
CREATE TABLE articles (
  id             text PRIMARY KEY,
  headline       text NOT NULL,
  details        text NOT NULL,
  attachment_url text,
  article_id     text,
  chunk_index    integer DEFAULT 0,
  embedding      vector(${dim}),                  -- dim from the embedding model
  created_at     timestamptz DEFAULT now()
);
CREATE INDEX articles_embedding_hnsw_idx          -- HNSW ANN index
  ON articles USING hnsw (embedding vector_cosine_ops);
```

`${dim}` comes from `EMBEDDING_DIM` (e.g. 384 for `multilingual-e5-small`). The
HNSW index uses `vector_cosine_ops`, matching the cosine operator below. A
singleton `model_meta` table (migration `005_model_meta.sql`) records the active
model name + dim and **rejects writes if the dimension changes** — preventing a
mixed-dimension table. Switching embedding model means re-embedding the whole
table (drop + recreate).

Two more migrations add the keyword paths:

```sql
-- 003_tsvector.sql — generated tsvector column + GIN index (powers /search/exact)
ALTER TABLE articles ADD COLUMN IF NOT EXISTS ts tsvector
  GENERATED ALWAYS AS (
    to_tsvector('english', coalesce(headline,'') || ' ' || coalesce(details,''))
  ) STORED;
CREATE INDEX IF NOT EXISTS articles_ts_gin_idx ON articles USING GIN (ts);

-- 004_trgm.sql — pg_trgm extension + trigram index (lexical, Thai-friendly)
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX IF NOT EXISTS articles_details_trgm_idx
  ON articles USING GIN (details gin_trgm_ops);
```

### The three SQL queries

**Dense (semantic)** — cosine distance via the `<=>` operator
(`PgVectorStore.search`):

```sql
SELECT id, article_id, chunk_index, headline, details, attachment_url,
       1 - (embedding <=> $1) AS score      -- cosine similarity (1 - distance)
FROM articles
ORDER BY embedding <=> $1                    -- nearest first; uses the HNSW index
LIMIT $2;
```

**Keyword FTS (Latin)** — `plainto_tsquery` + `ts_rank` over the generated `ts`
column (`searchExactFts` in `src/core/searchExact.js`):

```sql
SELECT article_id AS id, chunk_index, headline, details,
       ts_rank(ts, plainto_tsquery('english', $1)) AS score,
       ts_headline('english', headline || ' ' || details,
                   plainto_tsquery('english', $1), $2) AS snippet
FROM articles
WHERE ts @@ plainto_tsquery('english', $1)
ORDER BY article_id, ts_rank(...) DESC;
```

**Lexical trigram** — `word_similarity()` (pg_trgm) over `details`/`headline`,
used inside the hybrid pipeline and as the Thai fallback (`trigramScorer.js`).

Set up the stack with `docker-compose.yml` (Postgres + pgvector), then ingest so
the table is populated before searching.

---

## 3. Thai language handling

Thai is unspaced, so naive word tokenisation fails. The pipeline handles it at
four points:

**Embedding — multilingual by default.** The default embedder is
`Xenova/multilingual-e5-small` (`src/embeddings/index.js`, env `EMBEDDING_MODEL`),
a 384-dim multilingual sentence model that embeds Thai and English in one shared
space — so semantic (dense) search works on Thai with no extra config. Pooling is
mean + L2-normalised (`normalize: true`), which pairs with cosine distance in
Postgres. E5 models use the standard prefix convention — queries are embedded as
`query: <text>`, passages as `passage: <text>`.

**Normalisation** (`src/text/normalise.js`, gated by `textNormalisationEnabled`):

- Unicode **NFC** — merges decomposed Thai character sequences so visually
  identical text compares equal.
- Strips zero-width / formatting control chars (U+200B, U+00AD, bidi marks).
- Thai digits **๐–๙ → ASCII 0–9**.

Applied to both indexed text and the query before embedding.

**Chunking** (`src/data/chunker.js`). `chunkingMode` selects the strategy:
`length` (default, character windows of `chunkSize`/`chunkOverlap`) or
`thai_word`, which segments long Thai paragraphs with
`new Intl.Segmenter("th", { granularity: "word" })` and packs adjacent words up
to `chunkSize` — falling back to length-based chunking if the segmenter is
unavailable. Tune `chunkSize`/`chunkOverlap` for Thai density.

**Lexical / keyword for Thai.** Postgres `english` FTS cannot tokenise unspaced
Thai, so:

- **Hybrid lexical stage** uses **pg_trgm `word_similarity()`** — raw Unicode
  character trigrams, no segmentation (`trigramScorer.js`), which works for Thai
  and other unspaced scripts.
- **`/search/exact`** detects Thai script (`THAI_RE = /[฀-๿]/` in
  `searchExact.js`): Thai queries go through the **pg_trgm trigram scorer first**,
  then a **case-insensitive substring (ILIKE)** fallback — reserving
  `plainto_tsquery` FTS for Latin queries.

**Reranking** uses `bge-reranker-v2-m3`, a multilingual cross-encoder, so the
final stage also scores Thai query/passage pairs correctly.

A Thai evaluation set lives under `src/eval/` (`run_ablation.py`) for comparing
presets on recall/nDCG/MRR.

---

## 4. The three ranking-model options

Ranking quality is driven by three swappable model layers. Pick by the
quality/latency trade-off you want.

### Option A — Bi-encoder embedding (dense ranking)

Query and document are embedded **independently**; ranking = cosine similarity of
the two vectors. Fast (vectors are precomputed and ANN-indexed), good recall,
weaker precision on near-duplicates. Models in the registry
(`src/embeddings/model-registry.js`, env `EMBEDDING_MODEL`):

| Model | Dim | Notes |
|---|---|---|
| `Xenova/multilingual-e5-small` | 384 | **Default** — multilingual, fast |
| `multilingual-e5-base` | 768 | Higher quality, slower |
| `multilingual-e5-large` | 1024 | Best of the e5 family |
| `Xenova/all-MiniLM-L6-v2` | 384 | English-leaning, legacy |

Powers `dense-only` and the dense leg of hybrid.

### Option B — BGE-M3 (unified dense + sparse)

`BAAI/bge-m3` (`Xenova/bge-m3`, 1024-dim, `sparse: true`) produces **both** a
dense vector and lexical sparse weights from one model — hybrid retrieval without
a separate lexical scorer. Heavier than e5-small; strong multilingual coverage
including Thai.

### Option C — Cross-encoder reranker (`hybrid-rerank`)

`Xenova/bge-reranker-v2-m3` (`src/rerank/BgeRerankerV2M3.js`, env override
`RERANKER_MODEL_ID`) reads **query + passage jointly** through a transformer and
emits one relevance score per candidate — the highest-precision option, applied
to the top `rerankCandidateCount` (default 50) hits after fusion. Cost scales
with candidate count (one forward pass each). Primary path is the Transformers.js
ONNX pipeline (`text-classification`); a local **sidecar subprocess**
(`src/rerank/sidecar.js`, character n-gram scoring) is the fallback when the ONNX
model is unavailable.

**Rule of thumb:** A (bi-encoder) for speed and recall → B (BGE-M3) when you want
hybrid signal from a single model → C (cross-encoder) on top when precision at the
top of the list matters most.

---

## Related

- `src/config/retrieval.js` — preset registry, env var list, resolution order.
- `docs/architecture.md` — system map.
- README "Architecture" — file-backed mock vs. Milvus/Postgres status.
