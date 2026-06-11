"""
Tests for issue #28: /download route error message uses 'Attachment not found'
instead of 'Document not found'.

AC:
- /download returns 'Attachment not found' when file does not exist
- Change is in src/server.mjs
- All other /download behaviour (status codes, headers, successful downloads) unchanged
"""

import os
import pytest

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")
SERVER_MJS = os.path.join(PROJECT_ROOT, "src", "server.mjs")


# ---------------------------------------------------------------------------
# Static source checks (always run)
# ---------------------------------------------------------------------------

def test_source_contains_attachment_not_found():
    """AC2: 'Attachment not found' must appear in src/server.mjs."""
    with open(SERVER_MJS) as f:
        source = f.read()
    assert "Attachment not found" in source, (
        "Expected 'Attachment not found' in src/server.mjs"
    )


def test_source_has_no_document_not_found():
    """AC1/AC2: 'Document not found' must be removed from src/server.mjs."""
    with open(SERVER_MJS) as f:
        source = f.read()
    assert "Document not found" not in source, (
        "'Document not found' should not appear in src/server.mjs"
    )


# ---------------------------------------------------------------------------
# Live server acceptance tests (gated on UAT_BASE_URL)
# ---------------------------------------------------------------------------

import urllib.request
import urllib.error
import json

_UAT_BASE = os.environ.get("UAT_BASE_URL", "").rstrip("/")


@pytest.fixture
def uat_base():
    if not _UAT_BASE.startswith("http"):
        pytest.skip("UAT_BASE_URL not set — skipping live server tests")
    return _UAT_BASE


def _http_get(url):
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def test_uat_download_missing_file_returns_attachment_not_found(uat_base):
    """AC1: /download of a nonexistent file returns 404 with 'Attachment not found'."""
    status, body = _http_get(f"{uat_base}/download/nonexistent-article-zzz-28")
    assert status == 404
    data = json.loads(body)
    assert data.get("error") == "Attachment not found", (
        f"Expected 'Attachment not found', got: {data.get('error')!r}"
    )


def test_uat_download_missing_file_no_document_not_found(uat_base):
    """AC1: response must not contain the old 'Document not found' string."""
    status, body = _http_get(f"{uat_base}/download/nonexistent-article-zzz-28")
    assert "Document not found" not in body
