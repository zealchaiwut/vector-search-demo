-- Migration 003: Add generated tsvector column + GIN index for full-text search.
-- Idempotent: ADD COLUMN IF NOT EXISTS; CREATE INDEX IF NOT EXISTS.
--
-- This powers GET /search/exact via plainto_tsquery + ts_rank.

ALTER TABLE articles ADD COLUMN IF NOT EXISTS ts tsvector
  GENERATED ALWAYS AS (
    to_tsvector('english', coalesce(headline, '') || ' ' || coalesce(details, ''))
  ) STORED;

CREATE INDEX IF NOT EXISTS articles_ts_gin_idx ON articles USING GIN (ts);
