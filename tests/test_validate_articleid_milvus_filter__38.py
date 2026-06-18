"""Tests for issue #38: Validate or parameterize articleId in Milvus filter expressions (runs against UAT)

Risk: HIGH — security-related (injection prevention); touches articleValidation.js, collection.js, server.mjs.

AC1 - validateArticleId() exists and enforces an allow-list pattern (alphanumeric, hyphens, underscores)
AC2 - Endpoint handlers reject invalid articleId early with HTTP 400 and a descriptive error message
AC3 - No raw unvalidated articleId is interpolated into a Milvus filter at collection.js getArticle / deleteArticle
AC4 - Special characters (double-quote, backslash, %, *) are rejected before reaching the Milvus query layer
AC5 - Valid articleId values (e.g. 'abc-123', UUID) pass validation without regression

HTTP tests that require a live Node.js server are marked as skipped (Node.js not available in this env).
"""

import os
import re

import pytest
import httpx

# The coder clone holds the feature-branch source.
CODER_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "coder")
)
ARTICLE_VALIDATION_JS = os.path.join(CODER_DIR, "src", "data", "articleValidation.js")
COLLECTION_JS = os.path.join(CODER_DIR, "src", "data", "collection.js")
SERVER_MJS = os.path.join(CODER_DIR, "src", "server.mjs")

UAT_BASE_URL = os.environ.get("UAT_BASE_URL", "http://localhost:8001")


@pytest.fixture
def client():
    with httpx.Client(base_url=UAT_BASE_URL, timeout=10.0) as c:
        yield c


# ---------------------------------------------------------------------------
# AC1: validateArticleId() exists and enforces an allow-list pattern
# ---------------------------------------------------------------------------


def test_validate_articleid_milvus_filter__validation_function_exists():
    """AC1: articleValidation.js must export validateArticleId."""
    with open(ARTICLE_VALIDATION_JS) as f:
        src = f.read()
    assert "validateArticleId" in src, (
        "articleValidation.js does not define validateArticleId — "
        "the function was not added to the validation module"
    )
    assert re.search(r"export\s+function\s+validateArticleId", src), (
        "articleValidation.js does not export validateArticleId — "
        "the function must be exported so it can be imported by collection.js and server.mjs"
    )


def test_validate_articleid_milvus_filter__pattern_is_allowlist():
    """AC1: The pattern must be a strict allow-list (alphanumeric, hyphens, underscores only)."""
    with open(ARTICLE_VALIDATION_JS) as f:
        src = f.read()
    # Pattern must anchor start and end to prevent bypass via partial match
    assert re.search(r"ARTICLE_ID_PATTERN\s*=\s*/\^", src), (
        "ARTICLE_ID_PATTERN in articleValidation.js must start with '^' — "
        "missing start anchor allows prefix bypass"
    )
    assert re.search(r"ARTICLE_ID_PATTERN\s*=\s*/[^/]*\$/", src), (
        "ARTICLE_ID_PATTERN in articleValidation.js must end with '$' — "
        "missing end anchor allows suffix bypass"
    )


def test_validate_articleid_milvus_filter__rejects_empty_id():
    """AC1: validateArticleId must reject empty/falsy articleId."""
    with open(ARTICLE_VALIDATION_JS) as f:
        src = f.read()
    # The function body must handle falsy input
    assert re.search(r"if\s*\(\s*!articleId", src), (
        "validateArticleId does not guard against empty/falsy articleId — "
        "an empty string would produce an empty Milvus filter expression"
    )


# ---------------------------------------------------------------------------
# AC2: Endpoint handlers reject invalid articleId early with HTTP 400
# ---------------------------------------------------------------------------


def test_validate_articleid_milvus_filter__server_imports_validateArticleId():
    """AC2: server.mjs must import validateArticleId from articleValidation.js."""
    with open(SERVER_MJS) as f:
        src = f.read()
    assert re.search(r"import\s*\{[^}]*validateArticleId[^}]*\}\s*from", src), (
        "server.mjs does not import validateArticleId — "
        "the endpoint handler cannot validate the id without importing the function"
    )


def test_validate_articleid_milvus_filter__put_handler_validates_before_lookup():
    """AC2: PUT /articles/:id handler must call validateArticleId before getArticle."""
    with open(SERVER_MJS) as f:
        src = f.read()
    # Find the PUT /articles block
    put_block = re.search(
        r"// PUT /articles.*?(?=// (?:DELETE|GET|POST|HEAD)|$)",
        src,
        re.DOTALL,
    )
    assert put_block, "PUT /articles route block not found in server.mjs"
    block = put_block.group(0)
    # validateArticleId call must appear before getArticle
    vi = block.find("validateArticleId")
    ga = block.find("getArticle")
    assert vi != -1, "PUT /articles handler does not call validateArticleId"
    assert ga != -1, "PUT /articles handler does not call getArticle"
    assert vi < ga, (
        "PUT /articles handler calls getArticle before validateArticleId — "
        "validation must happen first to prevent injection"
    )


def test_validate_articleid_milvus_filter__delete_handler_validates_before_delete():
    """AC2: DELETE /articles/:id handler must call validateArticleId before deleteArticle."""
    with open(SERVER_MJS) as f:
        src = f.read()
    delete_block = re.search(
        r"// DELETE /articles.*?(?=// (?:GET|POST|HEAD|PUT)|$)",
        src,
        re.DOTALL,
    )
    assert delete_block, "DELETE /articles route block not found in server.mjs"
    block = delete_block.group(0)
    vi = block.find("validateArticleId")
    da = block.find("deleteArticle")
    assert vi != -1, "DELETE /articles handler does not call validateArticleId"
    assert da != -1, "DELETE /articles handler does not call deleteArticle"
    assert vi < da, (
        "DELETE /articles handler calls deleteArticle before validateArticleId — "
        "validation must happen first to prevent injection"
    )


def test_validate_articleid_milvus_filter__http_put_invalid_id_returns_400(client):
    """AC2: PUT /articles/<id-with-quotes> must return HTTP 400 — requires live Node.js server."""
    pytest.skip("requires live Node.js server — Node.js not installed in this environment")


def test_validate_articleid_milvus_filter__http_delete_invalid_id_returns_400(client):
    """AC2: DELETE /articles/<id-with-quotes> must return HTTP 400 — requires live Node.js server."""
    pytest.skip("requires live Node.js server — Node.js not installed in this environment")


# ---------------------------------------------------------------------------
# AC3: No raw unvalidated articleId in Milvus filter at getArticle / deleteArticle
# ---------------------------------------------------------------------------


def test_validate_articleid_milvus_filter__collection_imports_validateArticleId():
    """AC3: collection.js must import validateArticleId from ./articleValidation.js."""
    with open(COLLECTION_JS) as f:
        src = f.read()
    assert re.search(r"import\s*\{[^}]*validateArticleId[^}]*\}\s*from", src), (
        "collection.js does not import validateArticleId — "
        "without this import the Milvus functions cannot validate the id"
    )


def test_validate_articleid_milvus_filter__getArticle_validates_before_filter():
    """AC3: getArticle must call validateArticleId before constructing the Milvus filter."""
    with open(COLLECTION_JS) as f:
        src = f.read()
    get_block = re.search(
        r"export\s+async\s+function\s+getArticle.*?(?=export\s+async\s+function|$)",
        src,
        re.DOTALL,
    )
    assert get_block, "getArticle function not found in collection.js"
    block = get_block.group(0)
    vi = block.find("validateArticleId")
    fi = block.find("filter:")
    assert vi != -1, "getArticle does not call validateArticleId"
    assert fi != -1, "getArticle does not construct a Milvus filter — check implementation"
    assert vi < fi, (
        "getArticle constructs the Milvus filter before calling validateArticleId — "
        "raw user input must be validated first"
    )


def test_validate_articleid_milvus_filter__deleteArticle_validates_before_filter():
    """AC3: deleteArticle must call validateArticleId before constructing the Milvus filter."""
    with open(COLLECTION_JS) as f:
        src = f.read()
    del_block = re.search(
        r"export\s+async\s+function\s+deleteArticle.*?(?=export\s+async\s+function|$)",
        src,
        re.DOTALL,
    )
    assert del_block, "deleteArticle function not found in collection.js"
    block = del_block.group(0)
    vi = block.find("validateArticleId")
    fi = block.find("filter:")
    assert vi != -1, "deleteArticle does not call validateArticleId"
    assert fi != -1, "deleteArticle does not construct a Milvus filter"
    assert vi < fi, (
        "deleteArticle constructs the Milvus filter before calling validateArticleId"
    )


# ---------------------------------------------------------------------------
# AC4: Special characters are rejected before reaching the Milvus query layer
# ---------------------------------------------------------------------------


def _extract_article_id_pattern(src: str) -> str | None:
    """Extract the regex string from ARTICLE_ID_PATTERN = /.../ in JS source."""
    m = re.search(r"ARTICLE_ID_PATTERN\s*=\s*/([^/]+)/", src)
    return m.group(1) if m else None


def test_validate_articleid_milvus_filter__rejects_double_quote():
    """AC4: validateArticleId must reject an articleId containing a double-quote character."""
    with open(ARTICLE_VALIDATION_JS) as f:
        src = f.read()
    pattern_str = _extract_article_id_pattern(src)
    assert pattern_str is not None, "Could not extract ARTICLE_ID_PATTERN from articleValidation.js"
    pattern = re.compile(pattern_str)
    assert not pattern.match('abc"def'), (
        f"ARTICLE_ID_PATTERN ({pattern_str!r}) incorrectly accepts articleId with double-quote"
    )


def test_validate_articleid_milvus_filter__rejects_backslash():
    """AC4: validateArticleId must reject an articleId containing a backslash."""
    with open(ARTICLE_VALIDATION_JS) as f:
        src = f.read()
    pattern_str = _extract_article_id_pattern(src)
    assert pattern_str is not None, "Could not extract ARTICLE_ID_PATTERN from articleValidation.js"
    pattern = re.compile(pattern_str)
    assert not pattern.match("abc\\def"), (
        f"ARTICLE_ID_PATTERN ({pattern_str!r}) incorrectly accepts articleId with backslash"
    )


def test_validate_articleid_milvus_filter__rejects_injection_fragments():
    """AC4: validateArticleId must reject % and * (wildcard/injection characters)."""
    with open(ARTICLE_VALIDATION_JS) as f:
        src = f.read()
    pattern_str = _extract_article_id_pattern(src)
    assert pattern_str is not None, "Could not extract ARTICLE_ID_PATTERN from articleValidation.js"
    pattern = re.compile(pattern_str)
    for bad_id in ['%22 OR "1"="1', "abc%def", "abc*def", '%" OR "1"="1']:
        assert not pattern.match(bad_id), (
            f"ARTICLE_ID_PATTERN ({pattern_str!r}) incorrectly accepts injection fragment: {bad_id!r}"
        )


# ---------------------------------------------------------------------------
# AC5: Valid articleId values pass validation without regression
# ---------------------------------------------------------------------------


def test_validate_articleid_milvus_filter__accepts_hyphenated_id():
    """AC5: validateArticleId must accept valid ids with hyphens (e.g. 'abc-123')."""
    with open(ARTICLE_VALIDATION_JS) as f:
        src = f.read()
    pattern_str = _extract_article_id_pattern(src)
    assert pattern_str is not None, "Could not extract ARTICLE_ID_PATTERN from articleValidation.js"
    pattern = re.compile(pattern_str)
    assert pattern.match("abc-123"), (
        f"ARTICLE_ID_PATTERN ({pattern_str!r}) rejects 'abc-123' — valid hyphenated IDs must be accepted"
    )
    assert pattern.match("article-abc123"), (
        f"ARTICLE_ID_PATTERN ({pattern_str!r}) rejects 'article-abc123'"
    )


def test_validate_articleid_milvus_filter__accepts_uuid_format():
    """AC5: validateArticleId must accept UUIDs (alphanumeric + hyphens)."""
    with open(ARTICLE_VALIDATION_JS) as f:
        src = f.read()
    pattern_str = _extract_article_id_pattern(src)
    assert pattern_str is not None, "Could not extract ARTICLE_ID_PATTERN from articleValidation.js"
    pattern = re.compile(pattern_str)
    uuid_val = "550e8400-e29b-41d4-a716-446655440000"
    assert pattern.match(uuid_val), (
        f"ARTICLE_ID_PATTERN ({pattern_str!r}) rejects UUID {uuid_val!r} — "
        "UUIDs must be accepted as valid articleIds"
    )


def test_validate_articleid_milvus_filter__accepts_underscore_id():
    """AC5: validateArticleId must accept ids with underscores."""
    with open(ARTICLE_VALIDATION_JS) as f:
        src = f.read()
    pattern_str = _extract_article_id_pattern(src)
    assert pattern_str is not None, "Could not extract ARTICLE_ID_PATTERN from articleValidation.js"
    pattern = re.compile(pattern_str)
    assert pattern.match("my_article_123"), (
        f"ARTICLE_ID_PATTERN ({pattern_str!r}) rejects 'my_article_123' — underscored IDs must be accepted"
    )


def test_validate_articleid_milvus_filter__http_valid_id_not_rejected(client):
    """AC5: GET /articles with valid articleId must not return 400 — requires live Node.js server."""
    pytest.skip("requires live Node.js server — Node.js not installed in this environment")
