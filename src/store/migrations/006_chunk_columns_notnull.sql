-- Migration 006: enforce NOT NULL on article_id and chunk_index.
-- Follow-up to 002_chunk_columns.sql which adds the columns and backfills them.
-- Running this after 002 guarantees every existing row has a value, so the
-- constraint can be applied without a scan error.
-- Idempotent: SET NOT NULL is a no-op in PostgreSQL when the constraint already holds.

ALTER TABLE articles ALTER COLUMN article_id  SET NOT NULL;
ALTER TABLE articles ALTER COLUMN chunk_index SET NOT NULL;
