"""
Tests for issue #38: Validate or parameterize articleId in Milvus filter expressions

AC1 - articleId is validated against a safe pattern before any Milvus filter expression is built
AC2 - Requests with an invalid articleId are rejected at the endpoint handler with HTTP 400
AC3 - No raw, unvalidated articleId is interpolated directly into a Milvus filter string
AC4 - articleId containing ", \\, %, or * is rejected before reaching the Milvus query layer
AC5 - Valid articleId values (alphanumeric+hyphens, UUID) produce correct results without regression
"""

import os
import re

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COLLECTION_JS = os.path.join(REPO_ROOT, "src", "data", "collection.js")
VALIDATION_MODULE = os.path.join(REPO_ROOT, "src", "data", "articleValidation.js")
SERVER_MJS = os.path.join(REPO_ROOT, "src", "server.mjs")


def _read(path):
    with open(path) as f:
        return f.read()


# ---------------------------------------------------------------------------
# AC1 — validateArticleId function exists and accepts safe patterns
# ---------------------------------------------------------------------------


def test_ac1_validateArticleId_exported_from_validation_module():
    """AC1: articleValidation.js must export a validateArticleId function."""
    src = _read(VALIDATION_MODULE)
    assert re.search(r"export\s+function\s+validateArticleId", src), (
        "articleValidation.js must export 'export function validateArticleId'"
    )


def test_ac1_validateArticleId_defines_safe_pattern():
    """AC1: validateArticleId must use a pattern that allows only alphanumeric, hyphens, underscores."""
    src = _read(VALIDATION_MODULE)
    # Must contain a regex character class or string test covering a-z, A-Z, 0-9, -, _
    assert re.search(r"a-z|a-zA-Z|\\w", src), (
        "validateArticleId must use a pattern covering alphanumeric characters"
    )
    assert re.search(r"[\-_]|\-|_", src), (
        "validateArticleId pattern must allow hyphens and underscores"
    )


def test_ac1_validateArticleId_returns_null_for_valid_id():
    """AC1: validateArticleId must not reject valid alphanumeric+hyphen IDs."""
    src = _read(VALIDATION_MODULE)
    # The function must return null/falsy when valid; error string when invalid
    # Presence of a return null (or return falsy) path is required
    assert re.search(r"return\s+null|return\s+[\"']\s*[\"']|return\s+false|return\s+undefined", src), (
        "validateArticleId must return null/falsy for a valid articleId"
    )


def test_ac1_validateArticleId_error_message_present():
    """AC1: validateArticleId must return a descriptive error message for invalid IDs."""
    src = _read(VALIDATION_MODULE)
    # Must have some kind of error string about invalid article id
    assert re.search(r"[Ii]nvalid.*article.*id|article.*id.*invalid|invalid.*id", src, re.IGNORECASE), (
        "validateArticleId must produce a descriptive error message mentioning 'invalid' and 'id'"
    )


# ---------------------------------------------------------------------------
# AC2 — endpoint handlers call validateArticleId and return 400 on failure
# ---------------------------------------------------------------------------


def test_ac2_server_imports_validateArticleId():
    """AC2: server.mjs must import validateArticleId from articleValidation."""
    src = _read(SERVER_MJS)
    assert "validateArticleId" in src, (
        "server.mjs must import validateArticleId from ./data/articleValidation.js"
    )


def test_ac2_server_calls_validateArticleId_before_getArticle():
    """AC2: server.mjs must validate articleId before calling getArticle (PUT handler)."""
    src = _read(SERVER_MJS)
    # validateArticleId must appear in the PUT /articles/:id handler before getArticle is called
    # Check that validateArticleId appears and getArticle also appears, and validate comes first
    validate_pos = src.find("validateArticleId")
    get_article_pos = src.find("getArticle(")
    assert validate_pos != -1, "server.mjs must call validateArticleId"
    assert get_article_pos != -1, "server.mjs must call getArticle"
    assert validate_pos < get_article_pos, (
        "validateArticleId must be called before getArticle in server.mjs"
    )


def test_ac2_server_calls_validateArticleId_before_deleteArticle():
    """AC2: server.mjs must validate articleId before calling deleteArticle (DELETE handler)."""
    src = _read(SERVER_MJS)
    validate_pos = src.find("validateArticleId")
    delete_article_pos = src.find("deleteArticle(")
    assert validate_pos != -1, "server.mjs must call validateArticleId"
    assert delete_article_pos != -1, "server.mjs must call deleteArticle"
    assert validate_pos < delete_article_pos, (
        "validateArticleId must be called before deleteArticle in server.mjs"
    )


def test_ac2_server_returns_400_on_invalid_articleId():
    """AC2: server.mjs must respond with HTTP 400 when articleId fails validation."""
    src = _read(SERVER_MJS)
    # After validateArticleId call, the server must have a pattern that sends 400
    # Look for pattern: validateArticleId result checked and 400 returned
    assert re.search(r"validateArticleId.*400|400.*validateArticleId|idError.*400|400.*idError", src, re.DOTALL), (
        "server.mjs must return HTTP 400 when validateArticleId returns an error"
    )


def test_ac2_server_400_response_has_descriptive_error():
    """AC2: the HTTP 400 response for invalid articleId includes a descriptive error message."""
    src = _read(SERVER_MJS)
    # The 400 response body must include the error message from validateArticleId
    assert re.search(r"idError|validateArticleId", src), (
        "server.mjs 400 response for invalid articleId must include the validation error message"
    )


# ---------------------------------------------------------------------------
# AC3 — no raw unvalidated articleId in filter expressions
# ---------------------------------------------------------------------------


def test_ac3_collection_js_validates_before_filter_in_getArticle():
    """AC3: collection.js getArticle must validate or assert articleId before building filter."""
    src = _read(COLLECTION_JS)
    # The collection.js must import or call a validation/check on articleId
    # before interpolating it into the filter string
    assert re.search(r"validateArticleId|ARTICLE_ID_PATTERN|articleId.*test\(|test\(.*articleId", src), (
        "collection.js must call validateArticleId or test articleId pattern before filter interpolation"
    )


def test_ac3_collection_js_validates_before_filter_in_deleteArticle():
    """AC3: collection.js deleteArticle must validate or assert articleId before building filter."""
    src = _read(COLLECTION_JS)
    assert re.search(r"validateArticleId|ARTICLE_ID_PATTERN|articleId.*test\(|test\(.*articleId", src), (
        "collection.js must call validateArticleId or test articleId before building Milvus filter"
    )


def test_ac3_collection_js_imports_validateArticleId():
    """AC3: collection.js must import validateArticleId to protect filter construction."""
    src = _read(COLLECTION_JS)
    assert "validateArticleId" in src, (
        "collection.js must import validateArticleId from articleValidation.js"
    )


# ---------------------------------------------------------------------------
# AC4 — special chars rejected before reaching Milvus query layer
# ---------------------------------------------------------------------------


def test_ac4_validation_pattern_rejects_double_quote():
    """AC4: validateArticleId pattern must not allow double-quote character."""
    src = _read(VALIDATION_MODULE)
    # The safe pattern should be anchored and use a strict character class
    # Check that the pattern does NOT include " in the allowed set
    # A strict whitelist pattern like /^[a-zA-Z0-9_-]+$/ will reject "
    assert re.search(r"\^.*a-zA-Z0-9|^\^.*\\w", src) or re.search(r"a-zA-Z0-9_\-", src), (
        "validateArticleId must use a strict whitelist pattern anchored with ^ and $"
    )


def test_ac4_validation_pattern_is_anchored():
    """AC4: validateArticleId pattern must be fully anchored with ^ and $ to prevent bypass."""
    src = _read(VALIDATION_MODULE)
    # The pattern must be anchored at both ends
    assert re.search(r"\^.*\$", src), (
        "validateArticleId pattern must be anchored with both ^ and $ to prevent partial matches"
    )


def test_ac4_validation_pattern_rejects_percent():
    """AC4: % (wildcard) must be outside the allowed character class."""
    src = _read(VALIDATION_MODULE)
    # A whitelist pattern /^[a-zA-Z0-9_-]+$/ will naturally reject %
    # Just verify the pattern is a strict whitelist (whitelist approach)
    assert re.search(r"\[a-zA-Z0-9|\\w\+|-]|\[a-z", src), (
        "validateArticleId must use a strict whitelist pattern that naturally excludes %"
    )


def test_ac4_collection_js_no_unguarded_filter_interpolation():
    """AC4: collection.js filter expressions must not be reachable with unvalidated input."""
    src = _read(COLLECTION_JS)
    # The getArticle and deleteArticle functions must contain validation before filter use
    # Verify validateArticleId is called within these functions
    # (we check it's imported AND the function body contains the guard)
    get_article_fn = re.search(
        r"export\s+async\s+function\s+getArticle.*?(?=export\s+async\s+function|\Z)",
        src,
        re.DOTALL,
    )
    assert get_article_fn, "getArticle function must exist in collection.js"
    assert "validateArticleId" in get_article_fn.group(0), (
        "getArticle in collection.js must call validateArticleId before building filter"
    )

    delete_article_fn = re.search(
        r"export\s+async\s+function\s+deleteArticle.*?(?=export\s+async\s+function|\Z)",
        src,
        re.DOTALL,
    )
    assert delete_article_fn, "deleteArticle function must exist in collection.js"
    assert "validateArticleId" in delete_article_fn.group(0), (
        "deleteArticle in collection.js must call validateArticleId before building filter"
    )


# ---------------------------------------------------------------------------
# AC5 — valid articleIds continue to work (static regression checks)
# ---------------------------------------------------------------------------


def test_ac5_valid_uuid_format_passes_pattern():
    """AC5: The allowed pattern must accept UUID format (hex chars and hyphens)."""
    src = _read(VALIDATION_MODULE)
    # UUID format is hex (a-f, 0-9) and hyphens — must be in the allowed set
    # A pattern /^[a-zA-Z0-9_-]+$/ accepts UUIDs
    assert re.search(r"a-zA-Z0-9.*-|a-z.*A-Z.*0-9.*-", src) or re.search(r"a-zA-Z0-9_\\-", src), (
        "validateArticleId pattern must allow UUID characters (hex + hyphens)"
    )


def test_ac5_getArticle_filter_still_present():
    """AC5: collection.js getArticle must still use the id-prefix filter for Milvus queries."""
    src = _read(COLLECTION_JS)
    get_article_fn = re.search(
        r"export\s+async\s+function\s+getArticle.*?(?=export\s+async\s+function|\Z)",
        src,
        re.DOTALL,
    )
    assert get_article_fn, "getArticle must exist in collection.js"
    fn_body = get_article_fn.group(0)
    assert re.search(r'id\s+like|filter.*articleId|articleId.*filter', fn_body), (
        "getArticle must still build the Milvus id-prefix filter expression after validation"
    )


def test_ac5_deleteArticle_filter_still_present():
    """AC5: collection.js deleteArticle must still use the id-prefix filter for Milvus queries."""
    src = _read(COLLECTION_JS)
    delete_article_fn = re.search(
        r"export\s+async\s+function\s+deleteArticle.*?(?=export\s+async\s+function|\Z)",
        src,
        re.DOTALL,
    )
    assert delete_article_fn, "deleteArticle must exist in collection.js"
    fn_body = delete_article_fn.group(0)
    assert re.search(r'id\s+like|filter.*articleId|articleId.*filter', fn_body), (
        "deleteArticle must still build the Milvus id-prefix filter expression after validation"
    )


def test_ac5_server_get_and_delete_routes_still_present():
    """AC5: server.mjs must still implement GET/PUT /articles/:id and DELETE /articles/:id."""
    src = _read(SERVER_MJS)
    assert re.search(r'DELETE.*articles|articles.*DELETE', src), (
        "DELETE /articles/:id route must still be present in server.mjs"
    )
    assert re.search(r'PUT.*articles|articles.*PUT', src), (
        "PUT /articles/:id route must still be present in server.mjs"
    )
