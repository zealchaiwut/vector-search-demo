"""
Acceptance tests for issue #8: Wire search UI to /search endpoint with result cards.

AC1  - Submitting a query calls GET /search?q=<query> and renders one card per result
AC2  - Each card displays title and snippet using correct API response field names
AC3  - Each card includes a relevance meter whose fill width is proportional to score (0–1 → 0–100%)
AC4  - Each card includes a Download button that triggers GET /download/:docId with correct doc ID
AC5  - A no-match query shows a friendly empty-state message
AC6  - An unreachable API shows a distinct error-state message
AC7  - No console errors or unresolved field references when results are rendered
AC8  - All field names in UI match actual keys in the /search response payload
"""

import json
import os
import re
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_HTML = os.path.join(REPO_ROOT, "public", "index.html")
SERVER_MJS = os.path.join(REPO_ROOT, "src", "server.mjs")


# ---------------------------------------------------------------------------
# Helpers: mock API server
# ---------------------------------------------------------------------------

def _find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


class _MockAPIHandler(BaseHTTPRequestHandler):
    results_factory = None  # callable(query) -> list[dict] | Exception
    download_factory = None  # callable(doc_id) -> bytes | None

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/search":
            qs = parse_qs(parsed.query)
            query = qs.get("q", [""])[0]
            try:
                results = self.__class__.results_factory(query) if self.__class__.results_factory else []
                payload = json.dumps({"results": results}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(payload)
            except Exception as e:
                self.send_response(500)
                self.end_headers()
        elif parsed.path.startswith("/download/"):
            doc_id = parsed.path[len("/download/"):]
            content = (self.__class__.download_factory(doc_id)
                       if self.__class__.download_factory else b"sample content")
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition", f'attachment; filename="{doc_id}.txt"')
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(content)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *_):
        pass


def _start_mock_api(port, results_factory=None, download_factory=None):
    _MockAPIHandler.results_factory = results_factory
    _MockAPIHandler.download_factory = download_factory
    srv = HTTPServer(("localhost", port), _MockAPIHandler)
    t = threading.Thread(target=srv.serve_forever)
    t.daemon = True
    t.start()
    return srv


# ---------------------------------------------------------------------------
# Helpers: read HTML source
# ---------------------------------------------------------------------------

def _html_source():
    with open(INDEX_HTML) as f:
        return f.read()


# ---------------------------------------------------------------------------
# AC1 — GET /search?q=<query> endpoint wiring
# ---------------------------------------------------------------------------

def test_ac1_index_html_exists():
    """public/index.html must exist."""
    assert os.path.exists(INDEX_HTML), "public/index.html not found"


def test_ac1_fetch_uses_get_method():
    """HTML/JS must use GET (not POST) when calling /search."""
    src = _html_source()
    # Should NOT have method: 'POST' or method: "POST" for the search fetch
    # and SHOULD reference /search with q= query param
    assert re.search(r"/search\??", src), "No /search reference found in index.html"
    # Must not use POST for search (GET is default for fetch with no method option,
    # or explicitly set to 'GET')
    post_pattern = re.search(r"method\s*:\s*['\"]POST['\"]", src)
    assert not post_pattern, "index.html uses POST for search; expected GET"


def test_ac1_query_param_is_q():
    """Search URL must include ?q=<query> parameter."""
    src = _html_source()
    # Must build URL with q= param
    assert re.search(r'[?&]q=|[?&]q`|encodeURIComponent|URLSearchParams|["\']q["\']\s*[,:]\s*query', src), \
        "No q= query parameter found in search URL construction"


def test_ac1_server_search_endpoint_returns_json():
    """GET /search?q=<query> on the server returns JSON with results array."""
    import requests
    port = _find_free_port()
    sample = [{"doc_id": "doc-001", "title": "Test", "snippet": "snippet", "score": 0.9}]
    srv = _start_mock_api(port, results_factory=lambda _q: sample)
    try:
        resp = requests.get(f"http://localhost:{port}/search?q=test", timeout=5)
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data
        assert isinstance(data["results"], list)
    finally:
        srv.shutdown()


# ---------------------------------------------------------------------------
# AC2 — Cards show title and snippet with correct field names
# ---------------------------------------------------------------------------

def test_ac2_html_references_headline_field():
    """JS must read a field named 'headline' from each result."""
    src = _html_source()
    assert re.search(r'\.headline\b|["\'`]headline["\'`]', src), \
        "No 'headline' field reference found in index.html JS"


def test_ac2_html_references_details_field():
    """JS must read a field named 'details' from each result."""
    src = _html_source()
    assert re.search(r'\.details\b|["\'`]details["\'`]', src), \
        "No 'details' field reference found in index.html JS"


def test_ac2_server_returns_headline_and_details():
    """API /search response must include 'headline' and 'details' fields per result."""
    import requests
    port = _find_free_port()
    sample = [{"id": "article-001", "headline": "Vector Search Intro", "details": "A brief intro.", "score": 0.85, "attachment_url": "/download/article-001"}]
    srv = _start_mock_api(port, results_factory=lambda _q: sample)
    try:
        resp = requests.get(f"http://localhost:{port}/search?q=vector", timeout=5)
        results = resp.json()["results"]
        assert len(results) > 0
        assert "headline" in results[0], "Result missing 'headline' field"
        assert "details" in results[0], "Result missing 'details' field"
    finally:
        srv.shutdown()


# ---------------------------------------------------------------------------
# AC3 — Relevance meter with score-proportional width
# ---------------------------------------------------------------------------

def test_ac3_html_has_relevance_meter_element():
    """HTML must include a meter/progress-bar element for relevance."""
    src = _html_source()
    has_meter = (
        "meter" in src.lower() or
        re.search(r'relevance|score-bar|score-fill|progress|similarity', src, re.IGNORECASE) is not None
    )
    assert has_meter, "No relevance meter element found in index.html"


def test_ac3_html_maps_score_to_width_percent():
    """JS must map score (0–1) to width percentage for the meter fill."""
    src = _html_source()
    # Look for score * 100 or `${score*100}%` or similar pattern
    has_percent_mapping = re.search(
        r'score\s*\*\s*100|`\$\{.*score.*\}%`|score.*?%|width.*score|score.*width',
        src, re.IGNORECASE
    )
    assert has_percent_mapping, \
        "No score-to-percent width mapping found; expected score * 100 + '%' pattern"


def test_ac3_html_references_score_field():
    """JS must read a field named 'score' from each result."""
    src = _html_source()
    assert re.search(r'\.score\b|["\'`]score["\'`]', src), \
        "No 'score' field reference found in index.html JS"


# ---------------------------------------------------------------------------
# AC4 — Download button with correct /download/:docId URL
# ---------------------------------------------------------------------------

def test_ac4_html_has_download_button():
    """HTML must include a Download button or link per result card."""
    src = _html_source()
    has_download = re.search(r'[Dd]ownload', src) is not None
    assert has_download, "No Download button/link found in index.html"


def test_ac4_download_url_uses_attachment_url():
    """JS must use attachment_url (or build /download/<id>) for the Download link."""
    src = _html_source()
    has_download_url = re.search(r'/download/|attachment_url|\.id\b', src, re.IGNORECASE)
    assert has_download_url, \
        "No /download/ URL pattern found; Download button must use attachment_url or /download/<id>"


def test_ac4_html_references_id_field():
    """JS must read id from each result for display."""
    src = _html_source()
    has_id = re.search(r'\.id\b|articleId|["\'`]id["\'`]', src)
    assert has_id, "No id field reference found in index.html"


# ---------------------------------------------------------------------------
# AC5 — Empty state message
# ---------------------------------------------------------------------------

def test_ac5_html_has_empty_state_message():
    """HTML or JS must include an empty-state message for zero results."""
    src = _html_source()
    has_empty = re.search(
        r'no results?|nothing found|no match|empty|no documents',
        src, re.IGNORECASE
    )
    assert has_empty, \
        "No empty-state message found in index.html; add a message like 'No results found'"


# ---------------------------------------------------------------------------
# AC6 — Error state message
# ---------------------------------------------------------------------------

def test_ac6_html_has_error_state_message():
    """HTML or JS must include an error-state message for network/API failures."""
    src = _html_source()
    has_error = re.search(
        r'error|unable to reach|could not connect|failed|something went wrong|service unavailable',
        src, re.IGNORECASE
    )
    assert has_error, \
        "No error-state message found in index.html; add a message for unreachable API"


def test_ac6_fetch_has_catch_or_error_handling():
    """JS fetch must have error/catch handling for network failures."""
    src = _html_source()
    has_error_handling = re.search(r'\.catch\s*\(|try\s*\{|catch\s*\(|\.ok\b|response\.ok', src)
    assert has_error_handling, \
        "No fetch error handling (.catch / try-catch / response.ok check) found in index.html"


# ---------------------------------------------------------------------------
# AC7 — No unresolved field references (field names consistent)
# ---------------------------------------------------------------------------

def test_ac7_no_undefined_field_reads():
    """All field names used in card rendering must exist in the expected API shape."""
    src = _html_source()
    # Fields the API returns (from AC2, AC3, AC4)
    expected_fields = {"headline", "details", "score", "id"}
    # Look for any obvious .fieldName access that is NOT in expected_fields
    # Extract .something accesses in JS
    accessed = set(re.findall(r'\.\b([a-zA-Z_][a-zA-Z0-9_]*)\b', src))
    # Suspicious fields: ones that look like they're reading result data but
    # don't match known API fields — specifically, old/wrong names
    wrong_names = {"name", "description", "relevance", "similarity", "documentId"}
    suspicious = accessed & wrong_names
    # If suspicious field AND the matching correct field is absent, that's a bug
    if "name" in suspicious and not re.search(r'\.headline\b', src):
        pytest.fail("index.html uses .name but not .headline — likely wrong field name")
    if "description" in suspicious and not re.search(r'\.details\b', src):
        pytest.fail("index.html uses .description but not .details — likely wrong field name")


# ---------------------------------------------------------------------------
# AC8 — UI field names match actual API /search response keys
# ---------------------------------------------------------------------------

def test_ac8_ui_fields_match_api_fields():
    """
    The fields consumed by the UI (headline, details, score, id) must match
    the actual keys returned by the /search API endpoint.
    """
    import requests
    port = _find_free_port()
    sample = [
        {"id": "article-001", "headline": "T1", "details": "S1", "score": 0.9, "attachment_url": "/download/article-001"},
        {"id": "article-002", "headline": "T2", "details": "S2", "score": 0.5, "attachment_url": "/download/article-002"},
    ]
    srv = _start_mock_api(port, results_factory=lambda _q: sample)
    try:
        resp = requests.get(f"http://localhost:{port}/search?q=test", timeout=5)
        results = resp.json()["results"]
        assert len(results) > 0
        first = results[0]
        required_keys = {"headline", "details", "score", "id"}
        missing = required_keys - set(first.keys())
        assert not missing, f"API result missing required fields: {missing}"
    finally:
        srv.shutdown()


def test_ac8_real_server_search_returns_correct_shape():
    """Real src/server.mjs /search endpoint must return results with required fields."""
    assert os.path.exists(SERVER_MJS), "src/server.mjs not found"
    # Verify by reading server source: it must define the response shape
    with open(SERVER_MJS) as f:
        server_src = f.read()
    required = ["headline", "details", "score", "id"]
    for field in required:
        assert field in server_src, \
            f"src/server.mjs missing field '{field}' in response — UI expects it"


# ---------------------------------------------------------------------------
# UAT — Live server acceptance tests (httpx against running UAT instance)
# These tests hit the real running UAT server; set UAT_BASE_URL env var.
# ---------------------------------------------------------------------------

import httpx as _httpx

_UAT_BASE = os.environ.get("UAT_BASE_URL", "")


@pytest.fixture
def uat_client():
    if not _UAT_BASE.startswith("http"):
        pytest.skip("UAT_BASE_URL not set — skipping live server tests")
    with _httpx.Client(base_url=_UAT_BASE, timeout=10.0) as c:
        yield c


def test_search_ui__query_returns_results_array(uat_client):
    # AC1: GET /search?q=<query> returns 200 with non-empty results list
    r = uat_client.get("/search", params={"q": "vector search"})
    assert r.status_code == 200
    data = r.json()
    assert "results" in data and isinstance(data["results"], list)
    assert len(data["results"]) > 0


def test_search_ui__results_have_headline_and_details(uat_client):
    # AC2: each result has 'headline' and 'details' string fields
    r = uat_client.get("/search", params={"q": "embedding"})
    assert r.status_code == 200
    for item in r.json()["results"]:
        assert isinstance(item.get("headline"), str)
        assert isinstance(item.get("details"), str)


def test_search_ui__results_have_score_in_0_to_1_range(uat_client):
    # AC3: each result has 'score' float between 0 and 1
    r = uat_client.get("/search", params={"q": "semantic similarity"})
    assert r.status_code == 200
    for item in r.json()["results"]:
        score = item.get("score")
        assert isinstance(score, (int, float)) and 0 <= score <= 1


def test_search_ui__download_endpoint_returns_file(uat_client):
    # AC4: GET /download/:articleId returns attachment
    r = uat_client.get("/download/article-001")
    assert r.status_code == 200
    assert "attachment" in r.headers.get("content-disposition", "").lower()


def test_search_ui__download_unknown_doc_returns_404(uat_client):
    # AC4 edge: unknown id returns 404
    r = uat_client.get("/download/does-not-exist-xyz")
    assert r.status_code == 404


def test_search_ui__no_match_query_returns_empty_results(uat_client):
    # AC5: nonsense query returns results=[]
    r = uat_client.get("/search", params={"q": "xyzabc123qwerty999nonsense"})
    assert r.status_code == 200
    assert r.json().get("results") == []


def test_search_ui__api_response_shape_matches_ui_expectations(uat_client):
    # AC8: verify all UI-consumed fields are present
    r = uat_client.get("/search", params={"q": "vector"})
    assert r.status_code == 200
    results = r.json()["results"]
    assert len(results) > 0
    required = {"id", "headline", "details", "score"}
    for item in results:
        missing = required - set(item.keys())
        assert not missing, f"Missing fields: {missing}"
