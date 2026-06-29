"""
Shared path constants and assertion helpers for issue #98 static tests.

Both test_char_chunking__98.py (Node subprocess layer) and
test_chunk_documents_overlapping_segments__98.py (HTTP live-server layer)
performed identical static checks against chunker.js and migration SQL.
This module centralises those checks so any regex or path change only needs
to be made once.
"""
import os
import re

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHUNKER_JS = os.path.join(REPO_ROOT, "src", "data", "chunker.js")
PG_STORE_PATH = os.path.join(REPO_ROOT, "src", "store", "PgVectorStore.js")
MIGRATIONS_DIR = os.path.join(REPO_ROOT, "src", "store", "migrations")
DATA_EMBEDDER = os.path.join(REPO_ROOT, "src", "data", "embedder.js")


def read_all_migrations() -> str:
    """Concatenate all .sql files from MIGRATIONS_DIR in sorted order."""
    combined = ""
    for fname in sorted(f for f in os.listdir(MIGRATIONS_DIR) if f.endswith(".sql")):
        with open(os.path.join(MIGRATIONS_DIR, fname), encoding="utf-8") as fh:
            combined += fh.read() + "\n"
    return combined


def assert_migration_chunk_columns(sql: str) -> None:
    """Assert AC1: migration SQL defines the four chunk-schema columns."""
    assert re.search(r"article_id\s+text", sql, re.IGNORECASE), (
        "articles table must have article_id text column (FK for chunk grouping)"
    )
    assert re.search(r"chunk_index\s+integer", sql, re.IGNORECASE), (
        "articles table must have chunk_index integer column"
    )
    assert re.search(r"details\s+text", sql, re.IGNORECASE), (
        "articles table must have details text column for chunk content"
    )
    assert re.search(r"embedding\s+vector", sql, re.IGNORECASE), (
        "articles table must have embedding vector column"
    )


def assert_migration_preserves_article_metadata(sql: str) -> None:
    """Assert AC2: migration SQL retains headline and attachment_url; no DROP COLUMN."""
    assert re.search(r"headline\s+text", sql, re.IGNORECASE), (
        "articles table must retain headline text column"
    )
    assert "attachment_url" in sql.lower(), (
        "articles table must retain attachment_url column"
    )
    drops = re.findall(
        r"DROP\s+COLUMN\s+(headline|attachment_url|created_at)", sql, re.IGNORECASE
    )
    assert not drops, f"Migrations must not drop metadata columns; found: {drops}"


def assert_chunker_constants(src: str) -> None:
    """Assert AC3/AC8: CHUNK_SIZE and CHUNK_OVERLAP are exported named constants with
    correct approximate values; chunker.js does not use whitespace-based splitting."""
    assert re.search(r"export\s+(const\s+)?CHUNK_SIZE", src), (
        "chunker.js must export CHUNK_SIZE constant"
    )
    assert re.search(r"export\s+(const\s+)?CHUNK_OVERLAP", src), (
        "chunker.js must export CHUNK_OVERLAP constant"
    )

    size_match = re.search(r"CHUNK_SIZE\s*=\s*(\d+)", src)
    assert size_match, "CHUNK_SIZE must be defined as a numeric constant"
    assert 400 <= int(size_match.group(1)) <= 600, (
        f"CHUNK_SIZE should be ~500 chars, got {size_match.group(1)}"
    )

    overlap_match = re.search(r"CHUNK_OVERLAP\s*=\s*(\d+)", src)
    assert overlap_match, "CHUNK_OVERLAP must be defined as a numeric constant"
    assert 50 <= int(overlap_match.group(1)) <= 150, (
        f"CHUNK_OVERLAP should be ~100 chars, got {overlap_match.group(1)}"
    )

    word_splits = [line for line in src.splitlines() if re.search(r'\.split\s*\(\s*/\\s\+/', line)]
    assert not word_splits, (
        "chunker.js must not split by \\s+ — use character index slicing for Thai support"
    )
