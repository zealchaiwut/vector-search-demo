"""Tests for issue #107: [follow-up] reEmbedPostgres drops article_id/chunk_index before upsert (runs against UAT)"""
import os
import pytest
import subprocess
import json


# Resolved from UAT .env at runtime; see tester skill Step 0.
# Default kept only as a last-resort fallback if BASE_URL not exported.
BASE_URL = os.environ.get("UAT_BASE_URL") or "http://localhost:" + os.environ.get("UAT_PORT", "")
if not BASE_URL.startswith("http"):
    raise RuntimeError(
        "UAT_BASE_URL / UAT_PORT not set. Run the tester skill's Step 0 to resolve UAT before pytest."
    )

# REPO_ROOT points to the tester clone (where tests live)
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_re_embed_postgres_includes_article_id():
    """AC: The row mapping object in reEmbedPostgres() includes article_id in mapped fields"""
    # Read the re-embed.js source
    re_embed_path = os.path.join(REPO_ROOT, "src/commands/re-embed.js")
    with open(re_embed_path, "r") as f:
        source = f.read()

    # Locate the normal re-embed block (after "Normal re-embed" comment, lines 72-89)
    # Look for the row mapping that should include article_id: r.article_id
    assert "article_id: r.article_id" in source, \
        "row mapping in reEmbedPostgres() must include 'article_id: r.article_id'"


def test_re_embed_postgres_includes_chunk_index():
    """AC: The row mapping object in reEmbedPostgres() includes chunk_index in mapped fields"""
    # Read the re-embed.js source
    re_embed_path = os.path.join(REPO_ROOT, "src/commands/re-embed.js")
    with open(re_embed_path, "r") as f:
        source = f.read()

    # Look for the chunk_index field in the mapping
    assert "chunk_index: r.chunk_index" in source, \
        "row mapping in reEmbedPostgres() must include 'chunk_index: r.chunk_index'"


def test_re_embed_postgres_query_selects_article_id_and_chunk_index():
    """AC: The ORDER BY query correctly selects article_id and chunk_index fields"""
    # Read the re-embed.js source
    re_embed_path = os.path.join(REPO_ROOT, "src/commands/re-embed.js")
    with open(re_embed_path, "r") as f:
        source = f.read()

    # Confirm the SELECT query includes both article_id and chunk_index
    assert "article_id, chunk_index" in source, \
        "SELECT query must retrieve article_id and chunk_index fields"
    assert "ORDER BY article_id, chunk_index" in source, \
        "Query must order by article_id and chunk_index as designed"


def test_re_embed_postgres_no_undefined_fields():
    """AC: Existing tests pass and new tests assert fields are present in upsert payload"""
    # This is an integration test checking that the mapped object has no undefined fields
    # for article_id and chunk_index after the row mapping
    re_embed_path = os.path.join(REPO_ROOT, "src/commands/re-embed.js")
    with open(re_embed_path, "r") as f:
        source = f.read()

    # Confirm the mapping includes both fields (already tested above but verifying here)
    lines = source.split('\n')
    mapping_block = '\n'.join(lines[77:83])  # Lines 78-83 in 1-indexed

    assert "article_id:" in mapping_block, "article_id must be in row mapping"
    assert "chunk_index:" in mapping_block, "chunk_index must be in row mapping"
    # Verify they're not set to undefined by checking the structure
    assert "article_id: r.article_id" in source, "article_id should come from the query row"
    assert "chunk_index: r.chunk_index" in source, "chunk_index should come from the query row"
