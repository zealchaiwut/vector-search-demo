-- Migration 008: Add ts_simple tsvector column for OR-tsquery search with 'simple' dictionary.
--
-- The 'simple' dictionary lowercases tokens without stemming, making it suitable for:
--   - English OR queries where exact token forms matter
--   - Thai text pre-segmented with Intl.Segmenter (word tokens stored space-separated)
--
-- At ingest time, PgVectorStore.upsert() populates ts_simple with:
--   - English: to_tsvector('simple', headline || ' ' || details)
--   - Thai: to_tsvector('simple', <intl-segmenter word-joined text>)
--
-- The 'ts' column (migration 003) continues to serve English FTS with 'english' config.
-- ts_simple serves the OR-tsquery path for both languages.
--
-- Idempotent: ADD COLUMN IF NOT EXISTS; CREATE INDEX IF NOT EXISTS.

ALTER TABLE articles ADD COLUMN IF NOT EXISTS ts_simple tsvector;

-- Back-fill for existing rows using 'simple' tokenisation.
-- Thai rows inserted before this migration lack word-level segmentation here,
-- but will be correctly populated on the next PUT /articles upsert.
UPDATE articles
SET ts_simple = to_tsvector('simple', coalesce(headline, '') || ' ' || coalesce(details, ''))
WHERE ts_simple IS NULL;

CREATE INDEX IF NOT EXISTS articles_ts_simple_gin_idx ON articles USING GIN (ts_simple);
