-- Migration 001: articles table for pgvector backend
-- Idempotent: safe to run multiple times.
--
-- Recreate path (if you need a clean slate):
--   DROP TABLE IF EXISTS articles;
--   Then re-run this migration via `commander init`.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS articles (
  id             text PRIMARY KEY,
  headline       text NOT NULL,
  details        text NOT NULL,
  attachment_url text,
  embedding      vector(384),
  created_at     timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS articles_embedding_hnsw_idx
  ON articles
  USING hnsw (embedding vector_cosine_ops);
