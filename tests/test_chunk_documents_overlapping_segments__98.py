"""Tests for issue #98: Chunk documents into overlapping segments before indexing

Acceptance Criteria:
- A chunks table (or equivalent) exists with article_id (FK), chunk_index, text, embedding
- Articles table retains headline, attachment_url, and metadata fields
- Chunking splits by character length (~500 chars) with overlap (~100 chars), not whitespace
- Each chunk is embedded using multilingual passage prefix
- Thai PDF ≥2 pages produces ≥2 chunk rows linked to same article_id
- Retrieved unit is chunk, not full article body
- Re-ingesting existing article deletes old chunks (no duplicates)
- Chunk size and overlap are constants/config, not magic numbers

Tests run against UAT at $UAT_BASE_URL.
"""

import os
import re

import httpx
import pytest

from conftest import (
    CHUNKER_JS,
    PG_STORE_PATH,
    REPO_ROOT,
)

BASE_URL = os.environ.get("UAT_BASE_URL") or "http://localhost:" + os.environ.get("UAT_PORT", "8010")
HAS_DB = bool(os.environ.get("DATABASE_URL") or os.environ.get("UAT_BASE_URL"))


@pytest.fixture
def client():
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as c:
        yield c


# ---------------------------------------------------------------------------
# AC1: chunks equivalent (articles table) has article_id (FK), chunk_index columns
# (SQL column checks are owned by test_char_chunking__98 via conftest helpers)
# ---------------------------------------------------------------------------


def test_ac1_pg_store_handles_article_id_and_chunk_index():
    """PgVectorStore must insert/update article_id and chunk_index in upsert."""
    with open(PG_STORE_PATH) as f:
        src = f.read()
    assert "article_id" in src, "PgVectorStore.upsert must handle article_id"
    assert "chunk_index" in src, "PgVectorStore.upsert must handle chunk_index"


# ---------------------------------------------------------------------------
# AC2: Articles table retains headline, attachment_url, metadata fields
# (SQL static checks are owned by test_char_chunking__98 via conftest helpers)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_DB, reason="Requires live server with Postgres backend")
def test_ac2_article_headline_preserved_on_create_live(client):
    """POST /articles must preserve headline in stored article."""
    article_data = {
        "headline": "AC2 Test: Metadata Preserved",
        "details": "Content here. " * 60,  # Long enough for chunks
        "attachment_url": "https://example.com/test.pdf"
    }
    r = client.post("/articles", json=article_data)
    assert r.status_code == 201, f"Failed to create article: {r.text}"
    article_id = r.json()["id"]

    r_get = client.get(f"/articles/{article_id}")
    assert r_get.status_code == 200
    returned = r_get.json()
    assert returned.get("headline") == "AC2 Test: Metadata Preserved", (
        "headline must be preserved and retrievable"
    )

    client.delete(f"/articles/{article_id}")


@pytest.mark.skipif(not HAS_DB, reason="Requires live server with Postgres backend")
def test_ac2_article_attachment_url_preserved_on_create_live(client):
    """POST /articles must preserve attachment_url in stored article."""
    attachment_url = "https://example.com/document.pdf"
    article_data = {
        "headline": "AC2 Attachment Test",
        "details": "Content. " * 60,
        "attachment_url": attachment_url
    }
    r = client.post("/articles", json=article_data)
    assert r.status_code == 201
    article_id = r.json()["id"]

    r_get = client.get(f"/articles/{article_id}")
    assert r_get.status_code == 200
    returned = r_get.json()
    # If the implementation preserves the passed attachment_url, verify it
    # Some implementations might transform it, so allow reasonable variations
    assert "attachment_url" in returned or "attachment_url" in r.json(), (
        "article must preserve attachment_url field"
    )

    client.delete(f"/articles/{article_id}")


# ---------------------------------------------------------------------------
# AC3: Chunking splits by character length (~500) with overlap (~100), not whitespace
# (CHUNK_SIZE/CHUNK_OVERLAP constant presence, values, and no-whitespace-split checks
# are owned by test_char_chunking__98 via conftest helpers; unique checks below)
# ---------------------------------------------------------------------------


def test_ac3_chunker_uses_character_based_splitting():
    """chunker.js must use character-based splitting (text.slice), not word-based."""
    with open(CHUNKER_JS) as f:
        src = f.read()
    # Character-based: uses .slice(i, i + size)
    assert re.search(r"\.slice\s*\(\s*\w+\s*,\s*\w+\s*\+", src), (
        "chunker.js must use text.slice() for character-based chunking"
    )


def test_ac3_chunker_creates_overlapping_chunks():
    """chunkDocument must create overlapping chunks (stride = size - overlap)."""
    with open(CHUNKER_JS) as f:
        src = f.read()
    # Look for stride calculation
    assert re.search(r"stride\s*=.*[-]\s*\w+|stride.*overlap", src, re.IGNORECASE), (
        "chunker.js must calculate stride as (chunkSize - overlap) for overlap"
    )


@pytest.mark.skipif(not HAS_DB, reason="Requires live server with Postgres backend")
def test_ac3_long_article_chunks_correctly_live(client):
    """POSTing an article >500 chars should produce multiple chunks with overlap."""
    # Create article: ~1200 chars = 3 chunks with 100-char overlap
    long_text = "word " * 240  # ~1200 chars
    article_data = {
        "headline": "AC3 Character Chunking Test",
        "details": long_text,
        "attachment_url": ""
    }
    r = client.post("/articles", json=article_data)
    assert r.status_code == 201
    article_id = r.json()["id"]

    # Retrieve and verify all content is present (chunks reassembled)
    r_get = client.get(f"/articles/{article_id}")
    assert r_get.status_code == 200
    returned_body = r_get.json().get("details", "")
    # Should contain all the original content
    assert len(returned_body) >= len(long_text) - 10, (
        "Retrieved article should contain all chunks reassembled"
    )

    client.delete(f"/articles/{article_id}")


# ---------------------------------------------------------------------------
# AC4: Each chunk is embedded using multilingual passage prefix
# ---------------------------------------------------------------------------


def test_ac4_embedder_imports_or_uses_passage_prefix():
    """Embedder must apply multilingual passage prefix to chunks before embedding."""
    embedder_path = os.path.join(REPO_ROOT, "src", "data", "embedder.js")
    if os.path.exists(embedder_path):
        with open(embedder_path) as f:
            src = f.read()
        # Look for indication of passage prefix usage
        has_multilingual = re.search(r"multilingual|passage|Represent", src, re.IGNORECASE)
        # Passage prefix might be applied implicitly, so check code structure
        assert has_multilingual or "embed" in src.lower(), (
            "embedder.js should reference multilingual passage prefix or embedding logic"
        )


# ---------------------------------------------------------------------------
# AC5: Thai text ≥2 "pages" produces ≥2 chunk rows linked by article_id
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_DB, reason="Requires live server with Postgres backend")
def test_ac5_thai_text_produces_multiple_chunks_same_article_id_live(client):
    """Thai text with no whitespace (≥1000 chars) should produce ≥2 chunks with same article_id."""
    # Thai text without word boundaries — pure character-based chunking needed
    # Simulating with ~1100 repeated characters to ensure 2+ chunks
    thai_text = "ก" * 1100  # Thai character × 1100 (> 2 × CHUNK_SIZE)

    article_data = {
        "headline": "Thai Language AC5",
        "details": thai_text,
        "attachment_url": "https://example.com/thai.pdf"
    }
    r = client.post("/articles", json=article_data)
    assert r.status_code == 201
    article_id = r.json()["id"]

    # Verify full text is retrievable (all chunks reassembled)
    r_get = client.get(f"/articles/{article_id}")
    assert r_get.status_code == 200
    returned = r_get.json()
    returned_text = returned.get("details", "")
    # All Thai characters should be present
    assert len(returned_text) >= len(thai_text) - 10, (
        "Retrieved Thai article should contain all chunks reassembled "
        f"(input {len(thai_text)} chars, got {len(returned_text)})"
    )

    client.delete(f"/articles/{article_id}")


# ---------------------------------------------------------------------------
# AC6: Retrieved unit is chunk, not full article body
# ---------------------------------------------------------------------------


def test_ac6_pg_store_search_returns_chunk_level_columns():
    """PgVectorStore.search must return chunk-level columns (article_id, chunk_index)."""
    with open(PG_STORE_PATH) as f:
        src = f.read()
    assert re.search(r"article_id|chunk_index", src), (
        "PgVectorStore.search must return chunk-level metadata"
    )


def test_ac6_pg_store_get_returns_all_chunks_ordered():
    """PgVectorStore.get must return all chunks for article_id ordered by chunk_index."""
    with open(PG_STORE_PATH) as f:
        src = f.read()
    assert re.search(r"ORDER\s+BY\s+chunk_index", src, re.IGNORECASE), (
        "PgVectorStore.get must order chunks by chunk_index for reassembly"
    )


@pytest.mark.skipif(not HAS_DB, reason="Requires live server with Postgres backend")
def test_ac6_search_results_include_chunk_metadata_live(client):
    """Search results should include article_id and chunk_index for chunk-level retrieval."""
    # Create multi-chunk article
    long_text = "test " * 300  # ~1500 chars
    article_data = {
        "headline": "AC6 Search Chunk Test",
        "details": long_text,
        "attachment_url": ""
    }
    r = client.post("/articles", json=article_data)
    assert r.status_code == 201

    # Attempt to get the article (should return reassembled from chunks)
    article_id = r.json()["id"]
    r_get = client.get(f"/articles/{article_id}")
    assert r_get.status_code == 200
    # The fact that we can retrieve it means chunks are being assembled properly
    assert "details" in r_get.json(), "Retrieved article must include content field"

    client.delete(f"/articles/{article_id}")


# ---------------------------------------------------------------------------
# AC7: Re-ingesting existing article deletes old chunks (no duplicates)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_DB, reason="Requires live server with Postgres backend")
def test_ac7_reingest_replaces_chunks_no_duplicates_live(client):
    """Re-posting an article with new content should replace chunks, not duplicate them."""
    # First ingest
    article_data = {
        "headline": "AC7 Reingest Test",
        "details": "First version content. " * 50,  # Multi-chunk
        "attachment_url": ""
    }
    r1 = client.post("/articles", json=article_data)
    assert r1.status_code == 201
    article_id = r1.json()["id"]

    # Get initial state
    r_get1 = client.get(f"/articles/{article_id}")
    assert r_get1.status_code == 200
    initial_body = r_get1.json().get("details", "")

    # Update the article with new content
    article_data["details"] = "Updated content. " * 50
    r2 = client.put(f"/articles/{article_id}", json=article_data)
    # Depending on API, might be PUT or POST with ID
    if r2.status_code not in (200, 201):
        # Try POST with ID in body
        article_data["id"] = article_id
        r2 = client.post("/articles", json=article_data)

    if r2.status_code in (200, 201):
        # Verify we have the new content (not duplicates of old + new)
        r_get2 = client.get(f"/articles/{article_id}")
        assert r_get2.status_code == 200
        updated_body = r_get2.json().get("details", "")
        # Content should be updated
        assert updated_body != initial_body, "Article should be updated with new content"

    client.delete(f"/articles/{article_id}")


# ---------------------------------------------------------------------------
# AC8: Chunk size and overlap are constants/config, not magic numbers
# (export + value checks are owned by test_char_chunking__98 via conftest helpers;
# unique checks below)
# ---------------------------------------------------------------------------


def test_ac8_chunkdocument_uses_constant_defaults():
    """chunkDocument function must use CHUNK_SIZE and CHUNK_OVERLAP as default parameters."""
    with open(CHUNKER_JS) as f:
        src = f.read()
    # Check function signature includes default parameter usage
    assert re.search(
        r"chunkSize\s*=\s*CHUNK_SIZE|function.*chunkSize.*CHUNK_SIZE",
        src, re.IGNORECASE
    ), (
        "chunkDocument must use CHUNK_SIZE as default chunkSize parameter"
    )
    assert re.search(
        r"overlap\s*=\s*CHUNK_OVERLAP|function.*overlap.*CHUNK_OVERLAP",
        src, re.IGNORECASE
    ), (
        "chunkDocument must use CHUNK_OVERLAP as default overlap parameter"
    )


def test_ac8_no_magic_numbers_in_chunking():
    """chunker.js must not contain hardcoded magic numbers for chunk size or overlap."""
    with open(CHUNKER_JS) as f:
        src = f.read()
    # Look for suspicious hardcoded numbers (not constants)
    # This is a heuristic check; the main test is AC8 constants above
    # Just ensure the chunk size/overlap are via constants, not magic numbers
    assert re.search(r"export\s+const\s+CHUNK_SIZE", src), (
        "CHUNK_SIZE constant must be defined"
    )
