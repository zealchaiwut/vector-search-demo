"""
Tests for issue #41: Clarify articleId validation return semantics

The original function validateArticleId() has an inverted return convention:
  - returns null when valid (falsy = no error)
  - returns a string when invalid (truthy = error message)
The function name does not communicate that non-null means error.

Suggested fix (adopted): export getArticleIdError() as a clear-named alias so
callers read as `const err = getArticleIdError(id); if (err) ...`.

AC1 - getArticleIdError is exported from articleValidation.js and is identical
      in behaviour to validateArticleId (null on valid, error string on invalid)
AC2 - server.mjs call sites use getArticleIdError instead of validateArticleId
AC3 - milvus-store.js call sites use getArticleIdError instead of validateArticleId
AC4 - validateArticleId is still exported (backward compat; existing callers not broken)
"""

import os
import re

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VALIDATION_MODULE = os.path.join(REPO_ROOT, "src", "data", "articleValidation.js")
SERVER_MJS = os.path.join(REPO_ROOT, "src", "server.mjs")
MILVUS_STORE = os.path.join(REPO_ROOT, "src", "store", "milvus-store.js")


def _read(path):
    with open(path) as f:
        return f.read()


# ---------------------------------------------------------------------------
# AC1 — getArticleIdError exported from articleValidation.js
# ---------------------------------------------------------------------------


def test_ac1_getArticleIdError_exported():
    """AC1: articleValidation.js must export getArticleIdError."""
    src = _read(VALIDATION_MODULE)
    assert "getArticleIdError" in src, (
        "articleValidation.js must export getArticleIdError"
    )


def test_ac1_getArticleIdError_export_statement():
    """AC1: getArticleIdError must appear in an export statement."""
    src = _read(VALIDATION_MODULE)
    assert re.search(r"export\s+(function|const|let|var)\s+getArticleIdError|export\s*\{[^}]*getArticleIdError", src), (
        "articleValidation.js must have an explicit export for getArticleIdError"
    )


def test_ac1_getArticleIdError_returns_null_for_valid_id():
    """AC1: getArticleIdError must return null/falsy for a valid alphanumeric id."""
    src = _read(VALIDATION_MODULE)
    # The function body or aliased body returns null for valid input
    # (same behaviour as validateArticleId)
    assert re.search(r"return\s+null", src), (
        "articleValidation.js must have a 'return null' path for valid ids"
    )


def test_ac1_getArticleIdError_returns_string_for_invalid_id():
    """AC1: getArticleIdError must return a non-empty error string for an invalid id."""
    src = _read(VALIDATION_MODULE)
    assert re.search(r"[Ii]nvalid article id", src), (
        "articleValidation.js must return a descriptive error string for invalid ids"
    )


# ---------------------------------------------------------------------------
# AC2 — server.mjs call sites use getArticleIdError
# ---------------------------------------------------------------------------


def test_ac2_server_imports_getArticleIdError():
    """AC2: server.mjs must import getArticleIdError from articleValidation."""
    src = _read(SERVER_MJS)
    assert "getArticleIdError" in src, (
        "server.mjs must import or reference getArticleIdError"
    )


def test_ac2_server_call_sites_use_getArticleIdError():
    """AC2: every articleId validation call in server.mjs must use getArticleIdError."""
    src = _read(SERVER_MJS)
    # Count how many times getArticleIdError is called vs validateArticleId called
    get_err_calls = len(re.findall(r"getArticleIdError\(", src))
    validate_calls = len(re.findall(r"validateArticleId\(", src))
    assert get_err_calls >= 1, (
        "server.mjs must have at least one call to getArticleIdError()"
    )
    assert validate_calls == 0, (
        f"server.mjs call sites must use getArticleIdError, not validateArticleId "
        f"(found {validate_calls} remaining validateArticleId() calls)"
    )


def test_ac2_server_get_endpoint_uses_getArticleIdError():
    """AC2: GET /articles/:id handler in server.mjs uses getArticleIdError."""
    src = _read(SERVER_MJS)
    get_block = re.search(
        r'GET.*?/articles/.*?(?=if\s*\(req\.method\s*===\s*"PUT"|if\s*\(req\.method\s*===\s*"DELETE")',
        src,
        re.DOTALL,
    )
    assert get_block, "Could not locate GET /articles/:id block in server.mjs"
    assert "getArticleIdError" in get_block.group(0), (
        "GET /articles/:id handler must use getArticleIdError"
    )


def test_ac2_server_put_endpoint_uses_getArticleIdError():
    """AC2: PUT /articles/:id handler in server.mjs uses getArticleIdError."""
    src = _read(SERVER_MJS)
    put_block = re.search(
        r'PUT.*?/articles/.*?(?=if\s*\(req\.method\s*===\s*"DELETE")',
        src,
        re.DOTALL,
    )
    assert put_block, "Could not locate PUT /articles/:id block in server.mjs"
    assert "getArticleIdError" in put_block.group(0), (
        "PUT /articles/:id handler must use getArticleIdError"
    )


def test_ac2_server_delete_endpoint_uses_getArticleIdError():
    """AC2: DELETE /articles/:id handler in server.mjs uses getArticleIdError."""
    src = _read(SERVER_MJS)
    # Match specifically `req.method === "DELETE" && pathname.startsWith("/articles/")` block
    delete_block = re.search(
        r'req\.method\s*===\s*"DELETE"\s*&&\s*pathname\.startsWith.*?(?=if\s*\(req\.method|$)',
        src,
        re.DOTALL,
    )
    assert delete_block, "Could not locate DELETE /articles/:id handler block in server.mjs"
    assert "getArticleIdError" in delete_block.group(0), (
        "DELETE /articles/:id handler must use getArticleIdError"
    )


# ---------------------------------------------------------------------------
# AC3 — milvus-store.js call sites use getArticleIdError
# ---------------------------------------------------------------------------


def test_ac3_milvus_store_imports_getArticleIdError():
    """AC3: milvus-store.js must import getArticleIdError from articleValidation."""
    src = _read(MILVUS_STORE)
    assert "getArticleIdError" in src, (
        "milvus-store.js must import or reference getArticleIdError"
    )


def test_ac3_milvus_store_call_sites_use_getArticleIdError():
    """AC3: every articleId validation call in milvus-store.js must use getArticleIdError."""
    src = _read(MILVUS_STORE)
    validate_calls = len(re.findall(r"validateArticleId\(", src))
    get_err_calls = len(re.findall(r"getArticleIdError\(", src))
    assert get_err_calls >= 1, (
        "milvus-store.js must call getArticleIdError() at least once"
    )
    assert validate_calls == 0, (
        f"milvus-store.js call sites must use getArticleIdError, not validateArticleId "
        f"(found {validate_calls} remaining validateArticleId() calls)"
    )


# ---------------------------------------------------------------------------
# AC4 — validateArticleId still exported (backward compat)
# ---------------------------------------------------------------------------


def test_ac4_validateArticleId_still_exported():
    """AC4: articleValidation.js must still export validateArticleId for backward compat."""
    src = _read(VALIDATION_MODULE)
    assert re.search(r"export\s+function\s+validateArticleId", src), (
        "articleValidation.js must still export 'export function validateArticleId' "
        "so existing callers (collection.js) are not broken"
    )
