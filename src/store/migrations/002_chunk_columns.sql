-- Migration 002: add chunk-granularity columns to the articles table.
-- Idempotent: uses ADD COLUMN IF NOT EXISTS; safe to run against an existing database.
--
-- Recreate path (if you need a clean slate):
--   DROP TABLE IF EXISTS articles;
--   Then re-run all migrations via `commander init`.

ALTER TABLE articles ADD COLUMN IF NOT EXISTS article_id  text;
ALTER TABLE articles ADD COLUMN IF NOT EXISTS chunk_index integer DEFAULT 0;

-- Back-fill article_id and chunk_index from the existing id values.
-- id format is "<articleId>:<chunkIndex>" for chunked rows, or bare "<articleId>" for legacy rows.
UPDATE articles
SET
  article_id  = split_part(id, ':', 1),
  chunk_index = CASE
    WHEN position(':' IN id) > 0 THEN CAST(split_part(id, ':', 2) AS integer)
    ELSE 0
  END
WHERE article_id IS NULL;

CREATE INDEX IF NOT EXISTS articles_article_id_idx ON articles (article_id);
