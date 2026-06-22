"""
Tests for issue #82: Add exact-keyword search endpoint and Compare screen

AC1  - GET /search/exact?q=<query>&k=<limit> returns array with fields
       id, headline, details, score, attachment_url, best_passage
AC2  - GET /search/exact returns empty array (not error) when no document
       contains a lexical match for the query
AC3  - Keyword ranking uses ts_rank; document with an exact rare term ranks #1
AC4  - GIN index on tsvector column added via idempotent migration script
AC5  - public/index.html gains a Compare tab
AC6  - Compare screen renders two ranked lists side by side (Semantic / Keyword)
AC7  - Literal query terms highlighted in keyword-side cards
AC8  - Existing GET /search endpoint behavior and response shape unchanged
AC9  - npm run typecheck exits clean (structural: changed files must not use TS-only syntax)
"""

import os
import re
from urllib.parse import quote

import httpx
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_MJS = os.path.join(REPO_ROOT, "src", "server.mjs")
SEARCH_EXACT_JS = os.path.join(REPO_ROOT, "src", "core", "searchExact.js")
MIGRATIONS_DIR = os.path.join(REPO_ROOT, "src", "store", "migrations")
INDEX_HTML = os.path.join(REPO_ROOT, "public", "index.html")

BASE_URL = os.environ.get("UAT_BASE_URL") or (
    "http://localhost:" + os.environ.get("UAT_PORT", "8010")
)
HAS_DB = bool(os.environ.get("DATABASE_URL") or os.environ.get("UAT_BASE_URL"))


@pytest.fixture
def client():
    with httpx.Client(base_url=BASE_URL, timeout=15.0) as c:
        yield c


# ---------------------------------------------------------------------------
# AC1 + AC8: Static — server.mjs registers both /search and /search/exact
# ---------------------------------------------------------------------------


def test_ac1_server_registers_search_exact_route():
    """/search/exact route must be registered in server.mjs."""
    with open(SERVER_MJS) as f:
        src = f.read()
    assert re.search(r"/search/exact", src), (
        "server.mjs must define a handler for GET /search/exact"
    )


def test_ac1_searchexact_module_exists():
    """src/core/searchExact.js must exist."""
    assert os.path.exists(SEARCH_EXACT_JS), (
        "src/core/searchExact.js must exist — keyword search logic lives here"
    )


def test_ac1_searchexact_module_exports_function():
    """searchExact.js must export a function named searchExact."""
    with open(SEARCH_EXACT_JS) as f:
        src = f.read()
    assert re.search(r"export\s+(async\s+)?function\s+searchExact", src), (
        "searchExact.js must export a searchExact function"
    )


def test_ac1_searchexact_uses_ts_rank():
    """searchExact.js must use ts_rank for keyword ranking."""
    with open(SEARCH_EXACT_JS) as f:
        src = f.read()
    assert re.search(r"ts_rank", src, re.IGNORECASE), (
        "searchExact.js must use ts_rank for keyword ranking"
    )


def test_ac1_searchexact_uses_plainto_tsquery():
    """searchExact.js must use plainto_tsquery for safe FTS query parsing."""
    with open(SEARCH_EXACT_JS) as f:
        src = f.read()
    assert re.search(r"plainto_tsquery", src, re.IGNORECASE), (
        "searchExact.js must use plainto_tsquery to parse the keyword query"
    )


def test_searchexact_thai_uses_substring_match():
    """Thai script queries must use ILIKE substring search (english FTS misses Thai)."""
    with open(SEARCH_EXACT_JS) as f:
        src = f.read()
    assert re.search(r"ILIKE", src, re.IGNORECASE), (
        "searchExact.js must use ILIKE for Thai/non-Latin keyword matching"
    )
    assert re.search(r"THAI_RE|\\u0E00", src), (
        "searchExact.js must detect Thai script to route to substring search"
    )


def test_ac1_server_imports_search_exact():
    """server.mjs must reference searchExact (import or dynamic import)."""
    with open(SERVER_MJS) as f:
        src = f.read()
    assert "searchExact" in src, (
        "server.mjs must import/reference the searchExact function"
    )


# ---------------------------------------------------------------------------
# AC4: Migration adds tsvector column + GIN index (idempotent)
# ---------------------------------------------------------------------------


def _all_migration_sql():
    combined = ""
    for fname in sorted(f for f in os.listdir(MIGRATIONS_DIR) if f.endswith(".sql")):
        with open(os.path.join(MIGRATIONS_DIR, fname)) as fh:
            combined += fh.read() + "\n"
    return combined


def test_ac4_migration_adds_tsvector_column():
    """A migration must define a tsvector column (ts or similar)."""
    sql = _all_migration_sql()
    assert re.search(r"tsvector", sql, re.IGNORECASE), (
        "A migration file must add a tsvector column for full-text search"
    )


def test_ac4_migration_adds_gin_index():
    """A migration must create a GIN index on the tsvector column."""
    sql = _all_migration_sql()
    assert re.search(r"USING\s+GIN", sql, re.IGNORECASE), (
        "A migration file must create a GIN index (USING GIN) on the tsvector column"
    )


def test_ac4_migration_tsvector_idempotent():
    """Migration creating the tsvector column/index must be idempotent (IF NOT EXISTS)."""
    # Find the migration file(s) that contain tsvector
    for fname in sorted(f for f in os.listdir(MIGRATIONS_DIR) if f.endswith(".sql")):
        with open(os.path.join(MIGRATIONS_DIR, fname)) as fh:
            content = fh.read()
        if "tsvector" in content.lower():
            assert re.search(r"IF\s+NOT\s+EXISTS", content, re.IGNORECASE), (
                f"Migration {fname} adds a tsvector column/index but is not idempotent "
                "(missing IF NOT EXISTS)"
            )
            return
    pytest.fail("No migration file found that adds a tsvector column")


def test_ac4_migration_uses_to_tsvector():
    """Migration must use to_tsvector to build the search vector."""
    sql = _all_migration_sql()
    assert re.search(r"to_tsvector", sql, re.IGNORECASE), (
        "A migration must use to_tsvector to populate the tsvector column"
    )


# ---------------------------------------------------------------------------
# AC5: Compare tab exists in index.html
# ---------------------------------------------------------------------------


def test_ac5_compare_tab_button_exists():
    """public/index.html must have a tab button labeled 'Compare'."""
    with open(INDEX_HTML) as f:
        src = f.read()
    assert re.search(r"Compare", src), (
        "public/index.html must contain a Compare tab button"
    )
    assert re.search(r'id="tab-compare"', src), (
        "public/index.html must have a tab button with id='tab-compare'"
    )


def test_ac5_compare_panel_exists():
    """public/index.html must have a panel section for Compare."""
    with open(INDEX_HTML) as f:
        src = f.read()
    assert re.search(r'id="panel-compare"', src), (
        "public/index.html must have a panel with id='panel-compare'"
    )


# ---------------------------------------------------------------------------
# AC6: Side-by-side layout with Semantic (left) and Keyword (right) labels
# ---------------------------------------------------------------------------


def test_ac6_compare_semantic_column():
    """Compare panel must have a container labeled 'Semantic' for the left column."""
    with open(INDEX_HTML) as f:
        src = f.read()
    assert re.search(r"Semantic", src), (
        "Compare panel must label the semantic results column 'Semantic'"
    )
    assert re.search(r'id="compare-semantic"', src), (
        "Compare panel must have an element with id='compare-semantic' for semantic results"
    )


def test_ac6_compare_keyword_column():
    """Compare panel must have a container labeled 'Keyword' for the right column."""
    with open(INDEX_HTML) as f:
        src = f.read()
    assert re.search(r"Keyword", src), (
        "Compare panel must label the keyword results column 'Keyword'"
    )
    assert re.search(r'id="compare-keyword"', src), (
        "Compare panel must have an element with id='compare-keyword' for keyword results"
    )


def test_ac6_compare_fires_both_endpoints():
    """Compare JS must fetch both /search and /search/exact in parallel."""
    with open(INDEX_HTML) as f:
        src = f.read()
    assert re.search(r"/search/exact", src), (
        "Compare JS must fetch /search/exact"
    )
    assert re.search(r"Promise\.all", src), (
        "Compare JS must use Promise.all to fire both searches in parallel"
    )


def test_ac6_compare_grid_layout():
    """Compare panel CSS must define a two-column grid or flex layout."""
    with open(INDEX_HTML) as f:
        src = f.read()
    # Should have CSS for side-by-side columns
    assert re.search(r"grid-template-columns|flex.*row|compare-col", src), (
        "Compare panel CSS must define a side-by-side (grid or flex) layout"
    )


# ---------------------------------------------------------------------------
# AC7: Literal query term highlighting in keyword-side cards
# ---------------------------------------------------------------------------


def test_ac7_keyword_highlighting_in_compare():
    """Compare JS must highlight matched terms in keyword-side result cards."""
    with open(INDEX_HTML) as f:
        src = f.read()
    assert re.search(r"boldQueryWords|<b>|qw|\bkw\b|font-weight.*bold", src), (
        "Compare JS must highlight query terms in keyword-side result cards"
    )


def test_ac7_compare_keyword_uses_passages_array():
    """Compare keyword column must render stacked passages from the API."""
    with open(INDEX_HTML) as f:
        src = f.read()
    assert re.search(r"isKeyword[\s\S]*?r\.passages", src), (
        "Compare keyword rendering must iterate r.passages for multi-chunk keyword hits"
    )
    assert re.search(r"cmp-kw-snippet|class=\"kw\"", src), (
        "Compare keyword side must render FTS-matched term highlights (kw class)"
    )


def test_ac7_searchexact_returns_passages_array():
    """searchExact.js must return a passages array with html highlights per chunk."""
    with open(SEARCH_EXACT_JS) as f:
        src = f.read()
    assert "passages" in src, "searchExact.js must include passages in the response"
    assert re.search(r'MAX_CHUNKS_PER_ARTICLE\s*=\s*3', src), (
        "searchExact.js must cap keyword chunk hits at 3 per article"
    )
    assert re.search(r'<strong class="kw">', src), (
        "searchExact.js must convert Postgres <b> tags to strong.kw for matched terms"
    )


# ---------------------------------------------------------------------------
# AC8: Existing /search unchanged (static check)
# ---------------------------------------------------------------------------


def test_ac8_search_route_still_exists():
    """The existing GET /search route must still be present in server.mjs."""
    with open(SERVER_MJS) as f:
        src = f.read()
    assert re.search(r'pathname\s*===\s*["\']\/search["\']', src), (
        "server.mjs must still handle GET /search (existing search route must not be removed)"
    )


def test_ac8_searchDocuments_still_imported():
    """server.mjs must still import searchDocuments (original search function)."""
    with open(SERVER_MJS) as f:
        src = f.read()
    assert "searchDocuments" in src, (
        "server.mjs must still import and use searchDocuments for the existing /search endpoint"
    )


# ---------------------------------------------------------------------------
# AC9: No TypeScript-only syntax in changed JS files
# ---------------------------------------------------------------------------


def test_ac9_search_exact_no_ts_syntax():
    """searchExact.js must not contain TypeScript-only syntax."""
    with open(SEARCH_EXACT_JS) as f:
        src = f.read()
    assert not re.search(r"^interface\s+\w+", src, re.MULTILINE), (
        "searchExact.js must not contain TypeScript interface declarations"
    )
    assert not re.search(r"^type\s+\w+\s*=", src, re.MULTILINE), (
        "searchExact.js must not contain TypeScript type aliases"
    )


# ---------------------------------------------------------------------------
# Live tests (require running server with Postgres backend)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_DB, reason="Requires live server with Postgres backend")
def test_ac1_search_exact_returns_200_with_results(client):
    """GET /search/exact with a matching query must return HTTP 200 and a results array."""
    # First create a document so we have something to match
    headline = "Quarterly Revenue Report"
    details = "The quarterly revenue figures show strong growth in all segments."
    r = client.post("/articles", json={"headline": headline, "details": details, "attachment_url": ""})
    assert r.status_code == 201
    article_id = r.json()["id"]

    resp = client.get("/search/exact?q=quarterly+revenue&k=5")
    assert resp.status_code == 200
    data = resp.json()
    results = data.get("results", [])
    assert isinstance(results, list), "Response must contain a 'results' array"

    if results:
        r0 = results[0]
        assert "id" in r0, "Result must have 'id' field"
        assert "headline" in r0, "Result must have 'headline' field"
        assert "details" in r0, "Result must have 'details' field"
        assert "score" in r0, "Result must have 'score' field"
        assert "attachment_url" in r0, "Result must have 'attachment_url' field"
        assert "best_passage" in r0, "Result must have 'best_passage' field"
        assert isinstance(r0["score"], (int, float)), "score must be numeric"

    client.delete(f"/articles/{article_id}")


@pytest.mark.skipif(not HAS_DB, reason="Requires live server with Postgres backend")
def test_ac2_search_exact_empty_for_nonexistent_term(client):
    """GET /search/exact for a rare nonexistent term must return HTTP 200 with empty array."""
    resp = client.get("/search/exact?q=zzznonexistentterm9999&k=5")
    assert resp.status_code == 200
    data = resp.json()
    results = data.get("results", [])
    assert results == [], (
        "GET /search/exact must return an empty results array (not an error) when no matches found; "
        f"got: {results}"
    )


@pytest.mark.skipif(not HAS_DB, reason="Requires live server with Postgres backend")
def test_ac3_keyword_ranks_exact_term_first(client):
    """Document with an exact rare term must rank #1 on keyword side."""
    rare_term = "XQZRARESKU99182"
    r = client.post("/articles", json={
        "headline": f"Product {rare_term} specification",
        "details": f"This document describes the product with SKU {rare_term} in detail.",
        "attachment_url": "",
    })
    assert r.status_code == 201
    rare_id = r.json()["id"]

    # Also create a generic article that won't contain the rare term
    r2 = client.post("/articles", json={
        "headline": "General product overview",
        "details": "This is a generic article about products and specifications.",
        "attachment_url": "",
    })
    assert r2.status_code == 201
    generic_id = r2.json()["id"]

    resp = client.get(f"/search/exact?q={rare_term}&k=10")
    assert resp.status_code == 200
    results = resp.json().get("results", [])
    assert len(results) >= 1, f"Expected at least one result for rare term '{rare_term}'"
    assert results[0]["id"] == rare_id, (
        f"Document containing exact rare term '{rare_term}' must rank #1 on keyword side; "
        f"got: {[r['id'] for r in results[:3]]}"
    )

    client.delete(f"/articles/{rare_id}")
    client.delete(f"/articles/{generic_id}")


@pytest.mark.skipif(not HAS_DB, reason="Requires live server with Postgres backend")
def test_ac1_best_passage_contains_matched_term(client):
    """best_passage must contain text related to the searched term."""
    headline = "Revenue Analysis Document"
    details = "This report covers quarterly revenue performance and annual revenue targets."
    r = client.post("/articles", json={"headline": headline, "details": details, "attachment_url": ""})
    assert r.status_code == 201
    article_id = r.json()["id"]

    resp = client.get("/search/exact?q=revenue&k=5")
    assert resp.status_code == 200
    results = resp.json().get("results", [])
    matching = [r for r in results if r.get("id") == article_id]
    assert matching, "Created article must appear in results for 'revenue'"
    bp = matching[0].get("best_passage", "")
    assert bp, "best_passage must be non-empty for a matching document"
    # best_passage should contain text (either the snippet or article text)
    assert len(bp) > 5, f"best_passage should contain a meaningful snippet; got: {bp!r}"

    client.delete(f"/articles/{article_id}")


@pytest.mark.skipif(not HAS_DB, reason="Requires live server with Postgres backend")
def test_thai_keyword_substring_match(client):
    """Thai query terms must match via substring search when english FTS cannot tokenize."""
    thai_term = "ความปลอดภัย"
    details = (
        "ที่ ธน.(ว) IVB.224/2569 วันที่ 12 มีนาคม 2569 "
        "เรื่อง ความปลอดภัย ในการลงทุนเป็นสิ่งสำคัญสำหรับลูกค้า"
    )
    r = client.post(
        "/articles",
        json={"headline": "หนังสือแจ้งลูกค้า", "details": details, "attachment_url": ""},
    )
    assert r.status_code == 201
    article_id = r.json()["id"]

    resp = client.get(f"/search/exact?q={quote(thai_term)}&k=5")
    assert resp.status_code == 200
    results = resp.json().get("results", [])
    matching = [row for row in results if row.get("id") == article_id]
    assert matching, (
        f"Thai term {thai_term!r} must match via substring search; got {len(results)} results"
    )
    bp = matching[0].get("best_passage", "")
    assert thai_term in bp, f"best_passage must contain the Thai query term; got: {bp!r}"
    passages = matching[0].get("passages") or []
    assert passages, "Thai keyword hit must include passages array"
    assert any(thai_term in (p.get("text") or "") for p in passages), (
        "At least one passage snippet must contain the Thai query term"
    )

    client.delete(f"/articles/{article_id}")


@pytest.mark.skipif(not HAS_DB, reason="Requires live server with Postgres backend")
def test_ac8_search_endpoint_unchanged(client):
    """GET /search endpoint must still work and return the same response shape."""
    r = client.post("/articles", json={
        "headline": "Test article for regression",
        "details": "This is a test article to verify the existing search endpoint still works.",
        "attachment_url": "",
    })
    assert r.status_code == 201
    article_id = r.json()["id"]

    resp = client.get("/search?q=test+article+regression&k=5")
    assert resp.status_code == 200
    data = resp.json()
    assert "results" in data, "GET /search must return a 'results' key"
    results = data["results"]
    assert isinstance(results, list), "GET /search 'results' must be an array"
    if results:
        r0 = results[0]
        assert "id" in r0
        assert "headline" in r0
        assert "details" in r0
        assert "score" in r0
        assert "attachment_url" in r0

    client.delete(f"/articles/{article_id}")
