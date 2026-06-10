"""
Acceptance tests for issue #21: Replace Download button with external attachment link.

AC1 - GET /search response includes attachment_url on each result item
AC2 - Search result card renders an "Open" link using attachment_url as the href
AC3 - "Open" link has target="_blank" and rel="noopener" attributes
AC4 - No Download button appears anywhere in the search result card
AC5 - No calls to any /download route occur in the article/search flow
AC6 - Results where attachment_url is null/missing do not render a broken link
"""

import os
import re
import socket
import threading

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_HTML = os.path.join(REPO_ROOT, "public", "index.html")
SERVER_INDEX_TS = os.path.join(REPO_ROOT, "src", "server", "index.ts")
SEARCH_JS = os.path.join(REPO_ROOT, "src", "core", "search.js")


def _html_source():
    with open(INDEX_HTML) as f:
        return f.read()


def _extract_render_results_fn(src):
    """Return the substring of JS containing the renderResults function."""
    m = re.search(r'function renderResults\s*\(.*?\n\s*\}', src, re.DOTALL)
    return m.group(0) if m else src


# ---------------------------------------------------------------------------
# AC1 — GET /search includes attachment_url per result
# ---------------------------------------------------------------------------

def test_ac1_search_js_returns_attachment_url():
    """search.js searchDocuments must include attachment_url in its output map."""
    assert os.path.exists(SEARCH_JS), "src/core/search.js not found"
    with open(SEARCH_JS) as f:
        src = f.read()
    assert "attachment_url" in src, \
        "search.js must include attachment_url in the returned result objects"


def test_ac1_server_search_response_shape_includes_attachment_url():
    """server/index.ts SearchResult interface must declare attachment_url."""
    assert os.path.exists(SERVER_INDEX_TS), "src/server/index.ts not found"
    with open(SERVER_INDEX_TS) as f:
        src = f.read()
    assert "attachment_url" in src, \
        "server/index.ts SearchResult interface must include attachment_url field"


# ---------------------------------------------------------------------------
# AC2 — Card renders "Open" link with attachment_url as href
# ---------------------------------------------------------------------------

def test_ac2_render_results_uses_open_text():
    """renderResults must output a link labelled 'Open' (not 'Download')."""
    src = _html_source()
    render_fn = _extract_render_results_fn(src)
    assert re.search(r'\bOpen\b', render_fn), \
        "renderResults must include an 'Open' link label"


def test_ac2_render_results_uses_attachment_url_as_href():
    """renderResults must use attachment_url directly as the link href."""
    src = _html_source()
    render_fn = _extract_render_results_fn(src)
    assert re.search(r'attachment_url', render_fn), \
        "renderResults must reference attachment_url for the Open link href"


def test_ac2_open_link_is_anchor_element():
    """The Open link must be an <a> element (not a button)."""
    src = _html_source()
    render_fn = _extract_render_results_fn(src)
    assert re.search(r'<a\b.*?Open.*?</a>|<a\b.*?href.*?Open', render_fn, re.DOTALL), \
        "The Open link must be an anchor (<a>) element"


# ---------------------------------------------------------------------------
# AC3 — "Open" link has target="_blank" and rel="noopener"
# ---------------------------------------------------------------------------

def test_ac3_open_link_has_target_blank():
    """The Open link must have target=\"_blank\"."""
    src = _html_source()
    render_fn = _extract_render_results_fn(src)
    assert re.search(r'target\s*=\s*["\']_blank["\']', render_fn), \
        "Open link must have target=\"_blank\""


def test_ac3_open_link_has_rel_noopener():
    """The Open link must have rel=\"noopener\" (or \"noopener noreferrer\")."""
    src = _html_source()
    render_fn = _extract_render_results_fn(src)
    assert re.search(r'rel\s*=\s*["\'].*?noopener.*?["\']', render_fn), \
        "Open link must have rel=\"noopener\" (optionally with \"noreferrer\")"


# ---------------------------------------------------------------------------
# AC4 — No Download button in search result card
# ---------------------------------------------------------------------------

def test_ac4_no_download_button_in_render_results():
    """renderResults must not output any element labelled 'Download'."""
    src = _html_source()
    render_fn = _extract_render_results_fn(src)
    assert not re.search(r'\bDownload\b', render_fn), \
        "renderResults must not render a 'Download' button or link"


def test_ac4_no_download_attribute_in_render_results():
    """renderResults must not use the 'download' HTML attribute on any link."""
    src = _html_source()
    render_fn = _extract_render_results_fn(src)
    # 'download' HTML attribute looks like: <a ... download> or <a ... download="...">
    assert not re.search(r'\sdownload[\s>"\']', render_fn), \
        "renderResults must not use the HTML 'download' attribute"


# ---------------------------------------------------------------------------
# AC5 — No /download route fallback in card rendering
# ---------------------------------------------------------------------------

def test_ac5_no_download_route_fallback_in_render_results():
    """renderResults must not construct /download/<id> fallback URLs."""
    src = _html_source()
    render_fn = _extract_render_results_fn(src)
    assert not re.search(r'/download/', render_fn), \
        "renderResults must not fall back to /download/<id>; use attachment_url only"


def test_ac5_no_download_route_used_for_attachment_link():
    """The attachment link href must not reference any /download path."""
    src = _html_source()
    render_fn = _extract_render_results_fn(src)
    # The href must come directly from attachment_url, not a computed /download/ path
    assert not re.search(r'href.*?/download/', render_fn), \
        "Open link href must not reference /download/ path"


# ---------------------------------------------------------------------------
# AC6 — Null/missing attachment_url renders no broken link
# ---------------------------------------------------------------------------

def test_ac6_null_attachment_url_guarded_in_render_results():
    """renderResults must guard against null/missing attachment_url before rendering the link."""
    src = _html_source()
    render_fn = _extract_render_results_fn(src)
    # There must be a conditional: if attachment_url is truthy, render the link
    has_guard = bool(
        re.search(r'attachment_url\s*&&|attachment_url\s*\?|if\s*\(.*?attachment_url', render_fn) or
        re.search(r'\?\s*`.*?attachment_url|attachment_url.*?\?.*?:\s*["\']', render_fn, re.DOTALL)
    )
    assert has_guard, \
        "renderResults must conditionally render the Open link only when attachment_url is truthy"


def test_ac6_no_open_link_when_no_attachment():
    """When attachment_url is absent the card must not include an Open link."""
    src = _html_source()
    render_fn = _extract_render_results_fn(src)
    # The link must be inside a conditional block, not unconditionally rendered
    # Simplest check: the Open label must appear inside a ternary or if-block with attachment_url
    has_conditional_open = bool(
        re.search(
            r'attachment_url\s*[?&]{1,2}.*?Open|attachment_url.*?\?.*?Open|'
            r'if\s*\(.*?attachment_url.*?\).*?Open',
            render_fn, re.DOTALL
        )
    )
    assert has_conditional_open, \
        "The Open link must only appear when attachment_url is present (conditional render)"


# ---------------------------------------------------------------------------
# UAT — Live server acceptance tests
# ---------------------------------------------------------------------------

import httpx as _httpx

_UAT_BASE = os.environ.get("UAT_BASE_URL", "")


@pytest.fixture
def uat_client():
    if not _UAT_BASE.startswith("http"):
        pytest.skip("UAT_BASE_URL not set — skipping live server tests")
    with _httpx.Client(base_url=_UAT_BASE, timeout=10.0) as c:
        yield c


def test_uat_search_results_include_attachment_url(uat_client):
    """AC1: each /search result must include the attachment_url field."""
    r = uat_client.get("/search", params={"q": "vector"})
    assert r.status_code == 200
    results = r.json().get("results", [])
    assert len(results) > 0, "Need at least one result to check attachment_url field"
    for item in results:
        assert "attachment_url" in item, f"Result missing attachment_url: {item}"


def test_uat_no_download_route_called_in_search_flow(uat_client):
    """AC5: the /download route must not be needed; hitting it is a smell."""
    # We verify that the server does NOT redirect /search results through /download
    r = uat_client.get("/search", params={"q": "vector"})
    results = r.json().get("results", [])
    for item in results:
        url = item.get("attachment_url", "")
        assert "/download/" not in (url or ""), \
            f"attachment_url should not route through /download/: {url}"
