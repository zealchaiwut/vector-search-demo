-- Migration 007: chunk_embeddings table for multi-model corpus comparison.
-- Stores per-chunk, per-model dense vectors as real[] so models with different
-- output dimensions (e.g. 384-d and 1024-d) can coexist without schema changes.
--
-- Idempotent: CREATE TABLE IF NOT EXISTS; safe to run multiple times.
--
-- Usage:
--   embed-corpus --model BAAI/bge-m3
--   commander search --model BAAI/bge-m3 "my query"

CREATE TABLE IF NOT EXISTS chunk_embeddings (
  chunk_id   text    NOT NULL,
  model_id   text    NOT NULL,
  vector     real[]  NOT NULL,
  dimension  integer NOT NULL,
  created_at timestamptz DEFAULT now(),
  PRIMARY KEY (chunk_id, model_id)
);

CREATE INDEX IF NOT EXISTS chunk_embeddings_model_id_idx
  ON chunk_embeddings (model_id);
