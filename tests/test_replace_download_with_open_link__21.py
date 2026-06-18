"""Tests for issue #21: Replace Download button with external attachment link (runs against UAT)"""
import os
import re

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_HTML = os.path.join(REPO_ROOT, "public", "index.html")
SERVER_TS  = os.path.join(REPO_ROOT, "src", "server", "index.ts")
SEARCH_JS  = os.path.join(REPO_ROOT, "src", "core", "search.js")


def _html():
    with open(INDEX_HTML) as f:
        return f.read()


def _server_ts():
    with open(SERVER_TS) as f:
        return f.read()


def _search_js():
    with open(SEARCH_JS) as f:
        return f.read()


# ---------------------------------------------------------------------------
# AC1 — GET /search response includes attachment_url on each result item
# ---------------------------------------------------------------------------

def test_replace_download_with_open_link__search_js_returns_attachment_url():
    # AC1: core search module must propagate attachment_url from the row to the result
    src = _search_js()
    assert re.search(r'attachment_url', src), \
        "src/core/search.js does not reference attachment_url — field will be absent from results"


def test_replace_download_with_open_link__server_interface_has_attachment_url():
    # AC1: SearchResult interface in server/index.ts must declare attachment_url
    src = _server_ts()
    assert re.search(r'attachment_url', src), \
        "server/index.ts SearchResult interface missing attachment_url field"


# ---------------------------------------------------------------------------
# AC2 — Search result card renders an "Open" link using attachment_url as href
# ---------------------------------------------------------------------------

def test_replace_download_with_open_link__card_renders_open_text():
    # AC2: the card link must say "Open", not "Download"
    src = _html()
    # Look for the "Open" literal in the card rendering JS (renderResults function region)
    assert re.search(r"""["'`>]Open["'`<]""", src), \
        'index.html card does not render an "Open" link — text must be "Open"'


def test_replace_download_with_open_link__open_link_uses_attachment_url_as_href():
    # AC2: the href of the Open link must come from attachment_url, not a hardcoded /download/ path
    src = _html()
    # attachment_url must be used directly as the href value
    assert re.search(r'href[=\s]*["\$\{`].*attachment_url', src), \
        "index.html Open link href does not use attachment_url"
    # Must NOT fall back to /download/ for the open link
    # (a /download/ fallback for null case is explicitly banned by AC5)
    assert not re.search(r'attachment_url\s*\?\?\s*[`"\']?/?download/', src), \
        "index.html falls back to /download/ when attachment_url is null — violates AC5"


# ---------------------------------------------------------------------------
# AC3 — "Open" link has target="_blank" and rel="noopener" attributes
# ---------------------------------------------------------------------------

def test_replace_download_with_open_link__open_link_has_target_blank():
    # AC3: the link element must have target="_blank"
    src = _html()
    assert re.search(r'target\s*=\s*["\']_blank["\']|target.*_blank', src), \
        'index.html Open link missing target="_blank"'


def test_replace_download_with_open_link__open_link_has_rel_noopener():
    # AC3: the link must carry rel="noopener" (or "noopener noreferrer")
    src = _html()
    assert re.search(r'rel\s*=\s*["\']noopener|setAttribute.*rel.*noopener', src), \
        'index.html Open link missing rel="noopener"'


# ---------------------------------------------------------------------------
# AC4 — No Download button anywhere in the search result card
# ---------------------------------------------------------------------------

def test_replace_download_with_open_link__no_download_button_in_card():
    # AC4: the word "Download" must not appear as link/button text inside card rendering
    src = _html()
    # Isolate the renderResults function to avoid matching comments or non-card code
    render_match = re.search(r'function renderResults.*?(?=\n\s*async function|\n\s*function [a-zA-Z])', src, re.DOTALL)
    region = render_match.group(0) if render_match else src
    # "Download" as visible button/link label must be absent
    assert not re.search(r'[>"\']Download[<"\']', region), \
        'index.html still renders a "Download" label inside the search result card'


# ---------------------------------------------------------------------------
# AC5 — No calls to any /download route in the article/search flow
# ---------------------------------------------------------------------------

def test_replace_download_with_open_link__no_download_route_in_search_card():
    # AC5: /download/ must not be referenced in card URL construction
    src = _html()
    render_match = re.search(r'function renderResults.*?(?=\n\s*async function|\n\s*function [a-zA-Z])', src, re.DOTALL)
    region = render_match.group(0) if render_match else src
    assert not re.search(r'/download/', region), \
        "index.html renderResults references /download/ — search card must not call the download route"


# ---------------------------------------------------------------------------
# AC6 — Results where attachment_url is null/missing do not render a broken link
# ---------------------------------------------------------------------------

def test_replace_download_with_open_link__null_attachment_url_renders_no_link():
    # AC6: when attachment_url is null/falsy the card must not render any Open/Download link
    src = _html()
    render_match = re.search(r'function renderResults.*?(?=\n\s*async function|\n\s*function [a-zA-Z])', src, re.DOTALL)
    region = render_match.group(0) if render_match else src
    # The card must conditionally omit the link when attachment_url is absent.
    # A null-guarded link template: `${url ? `<a ...>` : ''}` or similar
    has_null_guard = re.search(
        r'attachment_url\s*\?\s*`?<a|attachment_url\s*&&\s*`?<a|attachment_url\s*\?\?\s*null|'
        r'if\s*\(.*attachment_url|attachment_url\s*\?\s*["\']',
        region
    )
    assert has_null_guard, \
        "index.html does not guard the Open link when attachment_url is null — a link is always rendered"


# ---------------------------------------------------------------------------
# UAT live server tests — skipped if UAT_BASE_URL not configured
# ---------------------------------------------------------------------------

import httpx as _httpx

_UAT_BASE = os.environ.get("UAT_BASE_URL", "")


@pytest.fixture
def uat_client():
    if not _UAT_BASE.startswith("http"):
        pytest.skip("UAT_BASE_URL not set — skipping live server tests")
    with _httpx.Client(base_url=_UAT_BASE, timeout=10.0) as c:
        yield c


def test_replace_download_with_open_link__uat_search_includes_attachment_url(uat_client):
    # AC1 live: GET /search returns attachment_url per result
    r = uat_client.get("/search", params={"q": "article"})
    assert r.status_code == 200, f"GET /search returned {r.status_code}"
    results = r.json().get("results", [])
    assert len(results) > 0, "No results returned — ingest data first"
    for item in results:
        assert "attachment_url" in item, f"Result missing attachment_url: {item.keys()}"


def test_replace_download_with_open_link__uat_download_route_not_used_in_search(uat_client):
    # AC5 live: /download/ endpoint should not be called by normal search flow;
    # verify the route still exists (backwards-compat) but returns 404 for unknown ids
    r = uat_client.get("/download/nonexistent-id-xyz")
    assert r.status_code == 404, \
        f"Expected 404 for unknown /download/ id, got {r.status_code}"
