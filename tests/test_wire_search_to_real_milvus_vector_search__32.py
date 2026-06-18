"""Tests for issue #32: Wire search to real Milvus vector search (runs against UAT)

Risk: MEDIUM — core ranking algorithm replaced across multiple files.

AC1 - src/core/search.js embeds the query using the same MiniLM model used at ingest
AC2 - Search executes via COSINE vector similarity with EF=64; TF-IDF no longer drives
      the main ranking
AC3 - Per-article chunk collapsing and best-passage extraction logic is preserved
AC4 - Response objects retain the shape: { id, headline, details, score,
      attachment_url, best_passage }
AC5 - searchDocuments is async (returns a Promise) and all call sites await it
AC6 - Querying an empty collection returns [] rather than throwing an error
AC7 - GET /search?q=<term> returns HTTP 200 (requires live Node.js server — skipped)
AC8 - CLI search <term> prints ranked results (requires Node.js runtime — skipped)
"""

import os
import re

import pytest
import httpx

# The coder clone holds the feature-branch source.
CODER_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "coder")
)
SEARCH_JS_PATH = os.path.join(CODER_DIR, "src", "core", "search.js")
SEARCH_CMD_PATH = os.path.join(CODER_DIR, "src", "commands", "search.js")
SERVER_MJS_PATH = os.path.join(CODER_DIR, "src", "server.mjs")
SERVER_INDEX_TS_PATH = os.path.join(CODER_DIR, "src", "server", "index.ts")
CLI_PATH = os.path.join(CODER_DIR, "src", "cli.js")

UAT_BASE_URL = os.environ.get("UAT_BASE_URL", "http://localhost:8001")


@pytest.fixture
def client():
    with httpx.Client(base_url=UAT_BASE_URL, timeout=10.0) as c:
        yield c


# ---------------------------------------------------------------------------
# AC1: search.js embeds the query using MiniLM (createEmbedder from embeddings/index.js)
# ---------------------------------------------------------------------------


def test_wire_search_to_real_milvus_vector_search__search_js_imports_create_embedder():
    """AC1: src/core/search.js must import createEmbedder from ../embeddings/index.js."""
    with open(SEARCH_JS_PATH) as f:
        src = f.read()
    assert "createEmbedder" in src, (
        "src/core/search.js does not reference createEmbedder — MiniLM query embedding missing"
    )
    assert re.search(r"from\s+['\"]\.\.\/embeddings\/index(?:\.js)?['\"]", src), (
        "src/core/search.js does not import from ../embeddings/index.js"
    )


def test_wire_search_to_real_milvus_vector_search__query_embedded_before_scoring():
    """AC1: search.js must call embedder.embed() to embed the query before scoring."""
    with open(SEARCH_JS_PATH) as f:
        src = f.read()
    assert re.search(r"await\s+\w*[Ee]mbedder\s*\.\s*embed\s*\(", src), (
        "src/core/search.js does not call embedder.embed() — query is not embedded with MiniLM"
    )


# ---------------------------------------------------------------------------
# AC2: COSINE similarity via stored embeddings (dotProduct); TF-IDF not used for ranking
# ---------------------------------------------------------------------------


def test_wire_search_to_real_milvus_vector_search__uses_dot_product_for_ranking():
    """AC2: Main ranking must use dense dot product (COSINE on pre-normalised embeddings)."""
    with open(SEARCH_JS_PATH) as f:
        src = f.read()
    assert "dotProduct" in src, (
        "src/core/search.js does not use dotProduct — dense vector scoring missing"
    )
    assert re.search(r"score\s*:\s*dotProduct\s*\(", src), (
        "src/core/search.js does not assign score via dotProduct()"
    )


def test_wire_search_to_real_milvus_vector_search__main_ranking_uses_stored_embeddings():
    """AC2: Scoring must operate on row.embedding (the stored MiniLM vectors), not TF-IDF."""
    with open(SEARCH_JS_PATH) as f:
        src = f.read()
    assert re.search(r"row\.embedding", src), (
        "src/core/search.js does not reference row.embedding — not using stored Milvus vectors"
    )


def test_wire_search_to_real_milvus_vector_search__ef64_overfetch():
    """AC2: Over-fetch factor must be EF=64."""
    with open(SEARCH_JS_PATH) as f:
        src = f.read()
    assert re.search(r"const\s+EF\s*=\s*64", src), (
        "src/core/search.js does not declare EF=64 constant"
    )
    assert re.search(r"\.slice\s*\(\s*0\s*,\s*EF\s*\)", src), (
        "src/core/search.js does not use EF for over-fetch slicing"
    )


# ---------------------------------------------------------------------------
# AC3: Chunk collapsing and best-passage extraction preserved
# ---------------------------------------------------------------------------


def test_wire_search_to_real_milvus_vector_search__chunk_collapsing_preserved():
    """AC3: Per-article chunk collapsing (best chunk per articleId) must still be present."""
    with open(SEARCH_JS_PATH) as f:
        src = f.read()
    # Expects a Map-based collapse by articleId or doc_id
    assert re.search(r"byArticleId|byDocId", src), (
        "src/core/search.js does not collapse chunks per article — collapsing logic removed"
    )


def test_wire_search_to_real_milvus_vector_search__best_passage_preserved():
    """AC3: selectBestPassage function must still be present for best_passage extraction."""
    with open(SEARCH_JS_PATH) as f:
        src = f.read()
    assert "selectBestPassage" in src, (
        "src/core/search.js does not define selectBestPassage — best_passage extraction removed"
    )
    assert re.search(r"const\s+best_passage\s*=\s*selectBestPassage\s*\(", src), (
        "src/core/search.js does not call selectBestPassage to build best_passage"
    )


# ---------------------------------------------------------------------------
# AC4: Response shape { id, headline, details, score, attachment_url, best_passage }
# ---------------------------------------------------------------------------


def test_wire_search_to_real_milvus_vector_search__response_has_required_fields():
    """AC4: Returned objects must include all required fields."""
    with open(SEARCH_JS_PATH) as f:
        src = f.read()
    # Match either `field:` (explicit value) or `field,`/`field\n` (ES6 shorthand)
    colon_fields = ["id", "headline", "details", "score", "attachment_url"]
    for field in colon_fields:
        assert re.search(rf"\b{field}\s*:", src), (
            f"src/core/search.js result object is missing field '{field}'"
        )
    # best_passage may appear as shorthand `best_passage,` or explicit `best_passage:`
    assert re.search(r"\bbest_passage\s*[,:\n}]", src), (
        "src/core/search.js result object is missing field 'best_passage'"
    )


# ---------------------------------------------------------------------------
# AC5: searchDocuments is async (returns a Promise); all call sites await it
# ---------------------------------------------------------------------------


def test_wire_search_to_real_milvus_vector_search__search_documents_returns_promise():
    """AC5: searchDocuments must return a Promise (inner impl is async)."""
    with open(SEARCH_JS_PATH) as f:
        src = f.read()
    # Either searchDocuments is declared async OR it delegates to an async helper
    has_async_export = bool(re.search(r"export\s+async\s+function\s+searchDocuments", src))
    has_async_impl = bool(re.search(r"async\s+function\s+_\w+", src))
    has_return_impl = bool(re.search(r"export\s+function\s+searchDocuments[^{]+\{[^}]*return\s+_\w+", src))
    assert has_async_export or (has_async_impl and has_return_impl), (
        "searchDocuments does not appear to return a Promise (neither declared async "
        "nor delegating to an async helper)"
    )


def test_wire_search_to_real_milvus_vector_search__server_mjs_awaits_search():
    """AC5: server.mjs must await the search/searchDocuments call."""
    with open(SERVER_MJS_PATH) as f:
        src = f.read()
    assert re.search(r"await\s+search\s*\(", src) or re.search(r"await\s+searchDocuments\s*\(", src), (
        "src/server.mjs does not await search() or searchDocuments()"
    )


def test_wire_search_to_real_milvus_vector_search__server_index_ts_awaits_search():
    """AC5: src/server/index.ts must await searchDocuments."""
    with open(SERVER_INDEX_TS_PATH) as f:
        src = f.read()
    assert re.search(r"await\s+searchDocuments\s*\(", src), (
        "src/server/index.ts does not await searchDocuments()"
    )


def test_wire_search_to_real_milvus_vector_search__search_cmd_is_async():
    """AC5: commands/search.js runSearch must be declared async."""
    with open(SEARCH_CMD_PATH) as f:
        src = f.read()
    assert re.search(r"export\s+async\s+function\s+runSearch", src), (
        "src/commands/search.js runSearch is not declared async"
    )


def test_wire_search_to_real_milvus_vector_search__cli_handles_runsearch_promise():
    """AC5: cli.js must await or .catch() the Promise returned by runSearch."""
    with open(CLI_PATH) as f:
        src = f.read()
    has_await = bool(re.search(r"await\s+runSearch\s*\(", src))
    has_chain = bool(re.search(r"runSearch\s*\(.*\)\s*\.\s*catch\s*\(", src))
    assert has_await or has_chain, (
        "cli.js does not await runSearch() or chain its Promise with .catch()"
    )


# ---------------------------------------------------------------------------
# AC6: Empty collection returns [] without error
# ---------------------------------------------------------------------------


def test_wire_search_to_real_milvus_vector_search__empty_collection_returns_empty_array():
    """AC6: When loadRows() returns [], searchDocuments must return [] immediately."""
    with open(SEARCH_JS_PATH) as f:
        src = f.read()
    # Expect an early-return guard after loading rows
    assert re.search(r"rows\.length\s*===\s*0\s*\)\s*return\s*\[\]", src) or \
           re.search(r"if\s*\(\s*rows\.length\s*===\s*0\s*\)\s*\{?\s*return\s*\[\]", src), (
        "src/core/search.js does not guard against empty rows with 'return []'"
    )


# ---------------------------------------------------------------------------
# AC7: GET /search?q=<term> returns HTTP 200 — requires live Node.js server
# ---------------------------------------------------------------------------


def test_wire_search_to_real_milvus_vector_search__http_search_returns_200():
    """AC7: GET /search?q=<term> must return HTTP 200 — requires live Node.js server."""
    pytest.skip(
        "manual — requires Node.js runtime and live vector-search-demo server; "
        "Node.js is not installed in this environment"
    )


# ---------------------------------------------------------------------------
# AC8: CLI search prints ranked results — requires Node.js runtime
# ---------------------------------------------------------------------------


def test_wire_search_to_real_milvus_vector_search__cli_prints_ranked_results():
    """AC8: CLI search <term> must print ranked results — requires Node.js runtime."""
    pytest.skip(
        "manual — requires Node.js runtime to execute the CLI; "
        "Node.js is not installed in this environment"
    )


# ---------------------------------------------------------------------------
# UAT smoke: Commander dashboard (UAT) is responding
# ---------------------------------------------------------------------------


def test_wire_search_to_real_milvus_vector_search__uat_server_responds(client):
    """Smoke: UAT server at UAT_BASE_URL responds to GET /."""
    r = client.get("/")
    assert r.status_code == 200
