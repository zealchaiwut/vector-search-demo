-- Migration 005: model_meta table for tracking the active embedding model and dimension.
-- Idempotent: CREATE TABLE IF NOT EXISTS; safe to run multiple times.
--
-- Purpose: detect dimension mismatches before they silently corrupt vector search.
-- When EMBEDDING_MODEL is changed, PgVectorStore.checkSchemaCompatibility() compares
-- the configured model's dimension against the stored dimension here and raises a
-- clear error if they differ, directing the operator to run:
--   commander re-embed --recreate
--
-- Migration path when changing EMBEDDING_MODEL:
--   1. Set the new EMBEDDING_MODEL in your .env.
--   2. Run: commander re-embed --recreate
--      This drops and recreates the articles table with the new vector dimension,
--      then re-embeds all stored documents with the new model.
--   3. The model_meta row is updated automatically.

CREATE TABLE IF NOT EXISTS model_meta (
  id          integer PRIMARY KEY DEFAULT 1,
  model_name  text    NOT NULL,
  dim         integer NOT NULL,
  updated_at  timestamptz DEFAULT now(),
  CONSTRAINT  model_meta_singleton CHECK (id = 1)
);
