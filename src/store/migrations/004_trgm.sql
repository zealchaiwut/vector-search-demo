-- Migration 004: Enable pg_trgm extension and add trigram index for lexical search.
--
-- pg_trgm operates on raw Unicode character trigrams — no word segmentation needed —
-- enabling similarity-based matching for Thai and other unspaced scripts.
--
-- Idempotent: CREATE EXTENSION IF NOT EXISTS; CREATE INDEX IF NOT EXISTS.
-- Safe to run on a fresh database or an existing one.

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX IF NOT EXISTS articles_details_trgm_idx
  ON articles
  USING GIN (details gin_trgm_ops);
