"""
Acceptance tests for issue #27: Clarify attachment URL resolution semantics in search results.

AC1 - The search response schema includes attachment_url_type: "external" | "local"
      alongside attachment_url so callers can discover which mode each result uses.
AC2 - The frontend renders attachment links correctly for both external URLs and
      local /download/ paths — either via the type discriminator or because the href
      always equals the raw attachment_url value.
AC3 - GET /download/<article-id> for a locally stored attachment returns HTTP 200
      with an appropriate Content-Type header.
AC4 - An external attachment_url stored on an article is preserved as-is in search
      results and remains a valid, clickable href.
AC5 - Articles with no attachment return attachment_url: null (or omitted/falsy)
      and the frontend renders no broken link.
"""

import os
import re
import json
import tempfile

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEARCH_JS = os.path.join(REPO_ROOT, "src", "core", "search.js")
SERVER_INDEX_TS = os.path.join(REPO_ROOT, "src", "server", "index.ts")
SERVER_MJS = os.path.join(REPO_ROOT, "src", "server.mjs")
INDEX_HTML = os.path.join(REPO_ROOT, "public", "index.html")


def _search_src():
    with open(SEARCH_JS) as f:
        return f.read()


def _server_ts_src():
    with open(SERVER_INDEX_TS) as f:
        return f.read()


def _server_mjs_src():
    with open(SERVER_MJS) as f:
        return f.read()


def _html_src():
    with open(INDEX_HTML) as f:
        return f.read()


def _extract_render_results_fn(src):
    m = re.search(r'function renderResults\s*\(.*?\n\s*\}', src, re.DOTALL)
    return m.group(0) if m else src


# ---------------------------------------------------------------------------
# AC1 — attachment_url_type field in search schema
# ---------------------------------------------------------------------------

def test_ac1_search_js_emits_attachment_url_type():
    """search.js must include attachment_url_type in the returned result objects."""
    src = _search_src()
    assert "attachment_url_type" in src, (
        "src/core/search.js must include attachment_url_type in result objects "
        "(should be 'external' | 'local' | null)"
    )


def test_ac1_server_ts_interface_declares_attachment_url_type():
    """server/index.ts SearchResult interface must declare attachment_url_type."""
    src = _server_ts_src()
    assert "attachment_url_type" in src, (
        "src/server/index.ts SearchResult interface must include attachment_url_type field"
    )


def test_ac1_attachment_url_type_helper_distinguishes_local_vs_external():
    """search.js must contain logic to discriminate /download/ paths as 'local'
    and full http(s) URLs as 'external'."""
    src = _search_src()
    # Must check for /download/ prefix OR http prefix to set the type
    has_local_check = bool(
        re.search(r'/download/', src) or
        re.search(r'startsWith.*download|download.*startsWith', src)
    )
    has_external_check = bool(
        re.search(r'http', src) and
        re.search(r'external|local', src)
    )
    assert has_local_check or has_external_check, (
        "search.js must contain logic to distinguish local (/download/) vs external attachment URLs"
    )


def test_ac1_attachment_url_type_values_are_correct_strings():
    """search.js must use exactly the string literals 'external' and 'local'."""
    src = _search_src()
    assert '"external"' in src or "'external'" in src, (
        "search.js must use the literal string 'external' for external attachment_url_type"
    )
    assert '"local"' in src or "'local'" in src, (
        "search.js must use the literal string 'local' for local attachment_url_type"
    )


# ---------------------------------------------------------------------------
# AC2 — Frontend renders both URL types correctly
# ---------------------------------------------------------------------------

def test_ac2_render_results_uses_attachment_url_as_href():
    """renderResults must use attachment_url directly as the link href (not rewrite it)."""
    src = _html_src()
    render_fn = _extract_render_results_fn(src)
    assert re.search(r'attachment_url|attachmentUrl', render_fn), (
        "renderResults must reference attachment_url or attachmentUrl for the link href"
    )


def test_ac2_render_results_does_not_hardcode_slash_download():
    """renderResults must not hard-code /download/ paths — URLs come from data."""
    src = _html_src()
    render_fn = _extract_render_results_fn(src)
    assert not re.search(r'["\']\/download\/', render_fn), (
        "renderResults must not hard-code /download/ as a literal string — "
        "attachment_url already carries the correct path"
    )


def test_ac2_null_attachment_renders_no_link():
    """renderResults must guard against null/missing attachment_url before rendering the link."""
    src = _html_src()
    render_fn = _extract_render_results_fn(src)
    has_guard = bool(
        re.search(r'attachment[Uu]rl\s*&&|attachment[Uu]rl\s*\?|if\s*\(.*?attachment', render_fn) or
        re.search(r'\?\s*`.*?attachment|attachment.*?\?.*?:\s*["\']', render_fn, re.DOTALL)
    )
    assert has_guard, (
        "renderResults must conditionally render the attachment link only when "
        "attachment_url is truthy — guard against null/missing values"
    )


# ---------------------------------------------------------------------------
# AC3 — /download/<article-id> returns 200 for locally stored attachment
# ---------------------------------------------------------------------------

def test_ac3_server_mjs_has_download_route():
    """/download/:articleId route must be present in server.mjs."""
    src = _server_mjs_src()
    assert "/download/" in src, (
        "server.mjs must have a /download/:articleId route"
    )


def test_ac3_server_ts_has_download_route():
    """/download/:docId route must be present in server/index.ts."""
    src = _server_ts_src()
    assert "/download/" in src, (
        "src/server/index.ts must have a /download/:docId route"
    )


def test_ac3_download_route_returns_404_for_nonexistent_in_source():
    """The /download route handler must return 404 when the file does not exist."""
    src = _server_mjs_src()
    # Must check existence and return 404
    assert "404" in src, (
        "server.mjs must return HTTP 404 when the requested attachment is not found"
    )
    assert re.search(r'existsSync|exists\(|readFile.*catch|not found', src, re.IGNORECASE), (
        "server.mjs /download handler must guard against missing files and return 404"
    )


def test_ac3_download_route_sets_content_type():
    """The /download route must set a Content-Type header."""
    src = _server_mjs_src()
    assert re.search(r'Content-Type|content-type|\.type\(', src), (
        "server.mjs /download route must set an appropriate Content-Type header"
    )


# ---------------------------------------------------------------------------
# AC4 — External attachment_url preserved in search results
# ---------------------------------------------------------------------------

def test_ac4_search_js_preserves_attachment_url_in_results():
    """search.js must include attachment_url in the returned result objects."""
    src = _search_src()
    assert "attachment_url" in src, (
        "search.js must include attachment_url in the result objects returned by searchDocuments"
    )


def test_ac4_external_url_type_classification():
    """search.js must classify http/https URLs as 'external' attachment_url_type."""
    src = _search_src()
    # There must be a path that produces "external" based on a URL with http
    assert re.search(r'http.*external|external.*http', src, re.DOTALL), (
        "search.js must classify http(s):// URLs as attachment_url_type 'external'"
    )


# ---------------------------------------------------------------------------
# AC5 — No regression: null attachment renders no broken link
# ---------------------------------------------------------------------------

def test_ac5_search_js_handles_null_attachment_url():
    """search.js must handle null or empty attachment_url gracefully."""
    src = _search_src()
    # Must not assume attachment_url is always set
    has_null_handling = bool(
        re.search(r'attachment_url.*\?\?|attachment_url.*null|null.*attachment_url', src) or
        re.search(r'attachment_url_type.*null|null.*attachment_url_type', src)
    )
    assert has_null_handling, (
        "search.js must handle null/empty attachment_url — e.g. use ?? null or guard"
    )


def test_ac5_open_link_conditional_in_render_results():
    """renderResults must only render the Open/attachment link when attachment_url is present."""
    src = _html_src()
    render_fn = _extract_render_results_fn(src)
    # Must have conditional rendering of the Open link
    has_conditional = bool(
        re.search(
            r'attachment[Uu]rl\s*[?&]{1,2}.*?Open|attachment[Uu]rl.*?\?.*?Open|'
            r'if\s*\(.*?attachment.*?\).*?Open',
            render_fn, re.DOTALL
        )
    )
    assert has_conditional, (
        "renderResults must only render the attachment link when attachment_url is truthy "
        "(null/empty attachment → no link)"
    )


# ---------------------------------------------------------------------------
# UAT — Live server acceptance tests (skipped when UAT_BASE_URL not set)
# ---------------------------------------------------------------------------

try:
    import httpx as _httpx
    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False

_UAT_BASE = os.environ.get("UAT_BASE_URL", "")

ATTACHMENTS_DIR = os.path.join(REPO_ROOT, "attachments")


@pytest.fixture
def uat_client():
    if not _HTTPX_AVAILABLE:
        pytest.skip("httpx not installed — skipping live server tests")
    if not _UAT_BASE.startswith("http"):
        pytest.skip("UAT_BASE_URL not set — skipping live server tests")
    with _httpx.Client(base_url=_UAT_BASE, timeout=10.0) as c:
        yield c


@pytest.fixture
def local_attachment_article(uat_client):
    """Create an article that maps to a local attachment file, yield its id, then clean up."""
    os.makedirs(ATTACHMENTS_DIR, exist_ok=True)

    # POST article
    r = uat_client.post(
        "/articles",
        json={
            "headline": "Local attachment test article",
            "details": "This article has a locally stored attachment for testing.",
            "attachment_url": "",  # will be set to /download/<id> after creation
        },
    )
    assert r.status_code == 201, f"Article creation failed: {r.text}"
    article_id = r.json()["id"]

    # Write local attachment file
    att_path = os.path.join(ATTACHMENTS_DIR, f"{article_id}.txt")
    with open(att_path, "w") as f:
        f.write("Local attachment content for testing issue #27.\n")

    # Update the article's attachment_url to point to /download/<id>
    r2 = uat_client.put(
        f"/articles/{article_id}",
        json={
            "headline": "Local attachment test article",
            "details": "This article has a locally stored attachment for testing.",
            "attachment_url": f"/download/{article_id}",
        },
    )
    assert r2.status_code == 200, f"Article update failed: {r2.text}"

    yield article_id

    # Cleanup
    uat_client.delete(f"/articles/{article_id}")
    if os.path.exists(att_path):
        os.remove(att_path)


@pytest.fixture
def external_attachment_article(uat_client):
    """Create an article with an external URL attachment, yield its id, then clean up."""
    r = uat_client.post(
        "/articles",
        json={
            "headline": "External URL attachment test article",
            "details": "This article has an external URL attachment for testing.",
            "attachment_url": "https://example.com/test-document.pdf",
        },
    )
    assert r.status_code == 201, f"Article creation failed: {r.text}"
    article_id = r.json()["id"]
    yield article_id
    uat_client.delete(f"/articles/{article_id}")


@pytest.fixture
def no_attachment_article(uat_client):
    """Create an article with no attachment, yield its id, then clean up."""
    r = uat_client.post(
        "/articles",
        json={
            "headline": "No attachment test article",
            "details": "This article has no attachment for testing.",
            "attachment_url": "",
        },
    )
    assert r.status_code == 201, f"Article creation failed: {r.text}"
    article_id = r.json()["id"]
    yield article_id
    uat_client.delete(f"/articles/{article_id}")


def test_uat_ac1_search_results_include_attachment_url_type(uat_client, local_attachment_article):
    """AC1: /search results must include attachment_url_type field."""
    r = uat_client.get("/search", params={"q": "locally stored attachment testing"})
    assert r.status_code == 200
    results = r.json().get("results", [])
    ids = [item["id"] for item in results]
    assert local_attachment_article in ids, (
        f"Article {local_attachment_article} not found in search results: {ids}"
    )
    for item in results:
        assert "attachment_url_type" in item, (
            f"Search result missing attachment_url_type field: {item}"
        )


def test_uat_ac1_local_attachment_has_type_local(uat_client, local_attachment_article):
    """AC1: article with /download/ attachment_url must have attachment_url_type='local'."""
    r = uat_client.get("/search", params={"q": "locally stored attachment testing"})
    assert r.status_code == 200
    results = r.json().get("results", [])
    matching = [item for item in results if item["id"] == local_attachment_article]
    assert matching, f"Article {local_attachment_article} not found in results"
    item = matching[0]
    assert item["attachment_url_type"] == "local", (
        f"Expected attachment_url_type='local' for /download/ URL, got: {item['attachment_url_type']}"
    )


def test_uat_ac3_download_local_attachment_returns_200(uat_client, local_attachment_article):
    """AC3: GET /download/<article-id> for locally stored file returns HTTP 200."""
    r = uat_client.get(f"/download/{local_attachment_article}")
    assert r.status_code == 200, (
        f"Expected 200 for /download/{local_attachment_article}, got {r.status_code}"
    )
    assert r.headers.get("content-type"), "Content-Type header missing from /download/ response"
    assert len(r.content) > 0, "/download/ response body is empty"


def test_uat_ac3_download_nonexistent_returns_404(uat_client):
    """AC3: GET /download/<nonexistent-id> returns HTTP 404, not a server error."""
    r = uat_client.get("/download/nonexistent-article-id-27-test")
    assert r.status_code == 404, (
        f"Expected 404 for non-existent attachment, got {r.status_code}"
    )


def test_uat_ac4_external_attachment_preserved_in_search(uat_client, external_attachment_article):
    """AC4: external attachment_url is preserved as-is in search results."""
    r = uat_client.get("/search", params={"q": "external URL attachment testing"})
    assert r.status_code == 200
    results = r.json().get("results", [])
    matching = [item for item in results if item["id"] == external_attachment_article]
    assert matching, f"Article {external_attachment_article} not found in results"
    item = matching[0]
    assert item["attachment_url"] == "https://example.com/test-document.pdf", (
        f"External attachment_url was not preserved: {item['attachment_url']}"
    )
    assert item["attachment_url_type"] == "external", (
        f"Expected attachment_url_type='external' for https:// URL, got: {item['attachment_url_type']}"
    )


def test_uat_ac5_no_attachment_returns_null(uat_client, no_attachment_article):
    """AC5: article with no attachment returns attachment_url=null (or falsy) in search results."""
    r = uat_client.get("/search", params={"q": "no attachment testing article"})
    assert r.status_code == 200
    results = r.json().get("results", [])
    matching = [item for item in results if item["id"] == no_attachment_article]
    assert matching, f"Article {no_attachment_article} not found in results"
    item = matching[0]
    assert not item.get("attachment_url"), (
        f"Expected null/falsy attachment_url for article with no attachment, got: {item['attachment_url']}"
    )
