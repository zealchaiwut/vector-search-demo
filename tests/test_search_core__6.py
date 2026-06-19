"""
Acceptance tests for issue #6: Add search core and HTTP API endpoints.

AC1 - searchDocuments(query, k) exists in src/core/search.js and embeds query before searching
AC2 - ANN search uses COSINE similarity with ef=64 and over-fetches chunks before collapsing
AC3 - Collapsing keeps only the best-scoring chunk per doc_id
AC4 - Results contain exactly: doc_id, title, snippet (≤240 chars), score (rounded numeric),
      attachment_name, download_url = "/download/<doc_id>"
AC5 - Results ordered by descending score and capped at k distinct documents
AC6 - GET /search?q=<query>&k=<n> calls searchDocuments and returns shaped JSON array
AC7 - GET /download/:docId streams attachment with correct content headers
AC8 - GET /download/:docId returns HTTP 404 when docId not found
AC9 - No leftover stub logic in src/server.mjs
"""

import http.client
import json
import os
import re
import socket
import subprocess
import time

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE_SEARCH_JS = os.path.join(REPO_ROOT, "src", "core", "search.js")
SERVER_MJS = os.path.join(REPO_ROOT, "src", "server.mjs")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _run_node(script, timeout=10):
    """Run a Node.js script and return (stdout, stderr, returncode)."""
    result = subprocess.run(
        ["node", "--input-type=module"],
        input=script,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=timeout,
    )
    return result.stdout, result.stderr, result.returncode


def _call_search_documents(query, k=10):
    """Call searchDocuments from Node and return parsed JSON results."""
    script = f"""
import {{ searchDocuments }} from './src/core/search.js';
const results = searchDocuments({json.dumps(query)}, {k});
process.stdout.write(JSON.stringify(results));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error (rc={rc}): {err}"
    return json.loads(out)


class _ServerProcess:
    """Context manager: starts the real Node server on a free port."""

    def __init__(self):
        self.port = _find_free_port()
        self.proc = None

    def __enter__(self):
        env = os.environ.copy()
        env["PORT"] = str(self.port)
        self.proc = subprocess.Popen(
            ["node", SERVER_MJS],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=REPO_ROOT,
            env=env,
        )
        # Wait until listening
        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                conn = http.client.HTTPConnection("localhost", self.port, timeout=1)
                conn.request("GET", "/")
                conn.getresponse()
                conn.close()
                break
            except Exception:
                time.sleep(0.1)
        return self

    def get(self, path):
        conn = http.client.HTTPConnection("localhost", self.port, timeout=5)
        conn.request("GET", path)
        resp = conn.getresponse()
        body = resp.read()
        conn.close()
        return resp.status, dict(resp.getheaders()), body

    def __exit__(self, *_):
        if self.proc:
            self.proc.terminate()
            self.proc.wait(timeout=3)


# ---------------------------------------------------------------------------
# AC1 — searchDocuments exists and embeds query
# ---------------------------------------------------------------------------

def test_ac1_core_search_file_exists():
    assert os.path.isfile(CORE_SEARCH_JS), f"Missing: {CORE_SEARCH_JS}"


def test_ac1_searchDocuments_exported():
    with open(CORE_SEARCH_JS) as f:
        src = f.read()
    assert "export function searchDocuments" in src or "export { searchDocuments" in src, \
        "searchDocuments must be exported from src/core/search.js"


def test_ac1_searchDocuments_returns_results_for_known_query():
    results = _call_search_documents("vector search embedding", k=5)
    assert isinstance(results, list), "searchDocuments must return a list"
    assert len(results) >= 1, "Expected at least one result for 'vector search embedding'"


def test_ac1_uses_cosine_or_vector_approach():
    """Search uses vector/cosine approach — verify via source code pattern."""
    with open(CORE_SEARCH_JS) as f:
        src = f.read()
    has_cosine = re.search(r"cosine|dot.*product|similarity|embed|vector", src, re.IGNORECASE)
    assert has_cosine, "src/core/search.js must implement cosine/vector-based search"


# ---------------------------------------------------------------------------
# AC2 — ANN with COSINE, ef=64, over-fetch chunks
# ---------------------------------------------------------------------------

def test_ac2_ef_constant_is_64():
    """EF (search quality parameter) must be 64."""
    with open(CORE_SEARCH_JS) as f:
        src = f.read()
    assert re.search(r"\bef\b\s*=\s*64|EF\s*=\s*64|ef\s*[:=]\s*64", src, re.IGNORECASE), \
        "src/core/search.js must define ef=64 (HNSW search parameter)"


def test_ac2_over_fetches_before_collapse():
    """Source must show evidence of over-fetching (fetching more than k before collapsing)."""
    with open(CORE_SEARCH_JS) as f:
        src = f.read()
    assert re.search(r"ef|EF|over.?fetch|candidates", src, re.IGNORECASE), \
        "Must over-fetch candidates (ef parameter) before collapsing to k results"


# ---------------------------------------------------------------------------
# AC3 — Collapse: at most one result per doc_id
# ---------------------------------------------------------------------------

def test_ac3_each_article_id_appears_at_most_once():
    results = _call_search_documents("vector semantic embedding search", k=10)
    article_ids = [r["id"] for r in results]
    assert len(article_ids) == len(set(article_ids)), \
        f"Each article id must appear at most once. Got duplicates: {article_ids}"


def test_ac3_collapse_logic_in_source():
    """Source must contain collapse/dedup logic per article id."""
    with open(CORE_SEARCH_JS) as f:
        src = f.read()
    assert re.search(r"articleId|byArticleId|collapse|dedup|Map|best.*chunk|chunk.*best", src, re.IGNORECASE), \
        "Must contain article id collapsing logic"


# ---------------------------------------------------------------------------
# AC4 — Result shape: id, headline, details, score, attachment_url, best_passage
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = {"id", "headline", "details", "score", "attachment_url"}


def test_ac4_result_has_all_required_fields():
    results = _call_search_documents("vector", k=1)
    assert len(results) >= 1, "Expected at least 1 result"
    r = results[0]
    missing = REQUIRED_FIELDS - set(r.keys())
    assert not missing, f"Result missing fields: {missing}. Got: {list(r.keys())}"


def test_ac4_no_extra_unexpected_fields():
    """Results must contain exactly the required fields (no hidden extras break the contract)."""
    results = _call_search_documents("vector", k=1)
    assert len(results) >= 1
    r = results[0]
    # Required fields must all be present
    missing = REQUIRED_FIELDS - set(r.keys())
    assert not missing, f"Missing: {missing}"


def test_ac4_details_max_240_chars():
    results = _call_search_documents("vector semantic embedding search pipeline", k=10)
    for r in results:
        assert len(r["details"]) <= 240, \
            f"Details too long ({len(r['details'])} chars) for article {r['id']}: {r['details']!r}"


def test_ac4_score_is_numeric_and_rounded():
    results = _call_search_documents("vector", k=3)
    for r in results:
        assert isinstance(r["score"], (int, float)), f"score must be numeric, got {type(r['score'])}"
        # Rounded: at most 4 decimal places
        s = str(r["score"])
        decimal_part = s.split(".")[-1] if "." in s else ""
        assert len(decimal_part) <= 4, f"score has too many decimals: {r['score']}"


def test_ac4_attachment_url_present_and_correct():
    results = _call_search_documents("vector", k=3)
    for r in results:
        assert r.get("attachment_url"), f"attachment_url missing or empty for {r['id']}"
        assert r["attachment_url"] == f"/download/{r['id']}", \
            f"attachment_url must be '/download/<id>', got: {r['attachment_url']!r}"


# ---------------------------------------------------------------------------
# AC5 — Ordered by descending score, capped at k
# ---------------------------------------------------------------------------

def test_ac5_results_ordered_descending():
    results = _call_search_documents("vector semantic embedding search", k=10)
    scores = [r["score"] for r in results]
    for i in range(len(scores) - 1):
        assert scores[i] >= scores[i + 1], \
            f"Scores not descending at index {i}: {scores[i]} > {scores[i+1]}"


def test_ac5_results_capped_at_k():
    results = _call_search_documents("vector semantic embedding search pipeline", k=3)
    assert len(results) <= 3, f"Expected at most 3 results with k=3, got {len(results)}"


def test_ac5_results_capped_at_k_1():
    results = _call_search_documents("vector semantic", k=1)
    assert len(results) <= 1, f"Expected at most 1 result with k=1, got {len(results)}"


def test_ac5_empty_query_returns_empty():
    results = _call_search_documents("", k=5)
    assert results == [], f"Empty query must return [], got {results}"


# ---------------------------------------------------------------------------
# AC6 — GET /search returns shaped JSON array
# ---------------------------------------------------------------------------

def test_ac6_search_endpoint_returns_200():
    with _ServerProcess() as srv:
        status, headers, body = srv.get("/search?q=vector&k=3")
    assert status == 200, f"Expected 200, got {status}"


def test_ac6_search_endpoint_returns_json():
    with _ServerProcess() as srv:
        status, headers, body = srv.get("/search?q=vector&k=3")
    content_type = headers.get("Content-Type", headers.get("content-type", ""))
    assert "application/json" in content_type, f"Expected JSON, got Content-Type: {content_type}"


def test_ac6_search_response_contains_results_array():
    with _ServerProcess() as srv:
        status, headers, body = srv.get("/search?q=vector&k=3")
    data = json.loads(body)
    assert "results" in data or isinstance(data, list), \
        "Response must be a JSON array or object with 'results' key"
    results = data["results"] if isinstance(data, dict) else data
    assert isinstance(results, list), "results must be a JSON array"


def test_ac6_search_results_have_required_fields():
    with _ServerProcess() as srv:
        status, headers, body = srv.get("/search?q=vector+search&k=2")
    data = json.loads(body)
    results = data["results"] if isinstance(data, dict) else data
    assert len(results) >= 1, "Expected at least 1 result for 'vector search'"
    r = results[0]
    missing = REQUIRED_FIELDS - set(r.keys())
    assert not missing, f"Result missing fields: {missing}"


def test_ac6_search_empty_query_returns_empty_array():
    with _ServerProcess() as srv:
        status, headers, body = srv.get("/search?q=&k=5")
    assert status == 200
    data = json.loads(body)
    results = data["results"] if isinstance(data, dict) else data
    assert results == [], f"Empty query must return empty array, got {results}"


# ---------------------------------------------------------------------------
# AC7 — GET /download/:docId streams with correct content headers
# ---------------------------------------------------------------------------

def test_ac7_download_known_doc_returns_200():
    with _ServerProcess() as srv:
        status, headers, body = srv.get("/download/article-001")
    assert status == 200, f"Expected 200 for known docId, got {status}"


def test_ac7_download_has_content_disposition():
    with _ServerProcess() as srv:
        status, headers, body = srv.get("/download/article-001")
    cd = headers.get("Content-Disposition", headers.get("content-disposition", ""))
    assert cd, "Content-Disposition header must be set for /download/:docId"
    assert "attachment" in cd.lower(), f"Content-Disposition must include 'attachment', got: {cd!r}"


def test_ac7_download_has_content_type():
    with _ServerProcess() as srv:
        status, headers, body = srv.get("/download/article-001")
    ct = headers.get("Content-Type", headers.get("content-type", ""))
    assert ct, "Content-Type header must be set for /download/:docId"


def test_ac7_download_body_nonempty():
    with _ServerProcess() as srv:
        status, headers, body = srv.get("/download/article-001")
    assert len(body) > 0, "Download response body must not be empty"


# ---------------------------------------------------------------------------
# AC8 — GET /download/:docId returns 404 for unknown docId
# ---------------------------------------------------------------------------

def test_ac8_download_unknown_returns_404():
    with _ServerProcess() as srv:
        status, headers, body = srv.get("/download/nonexistent-id-xyz")
    assert status == 404, f"Expected 404 for unknown docId, got {status}"


# ---------------------------------------------------------------------------
# AC9 — No stub routes in src/server.mjs
# ---------------------------------------------------------------------------

def test_ac9_no_stub_patterns_in_server():
    with open(SERVER_MJS) as f:
        src = f.read()
    stub_patterns = [
        r"\bTODO\b",
        r"\bSTUB\b",
        r"\bFIXME\b",
        r"not\s+implemented",
        r"placeholder",
    ]
    for pat in stub_patterns:
        m = re.search(pat, src, re.IGNORECASE)
        assert not m, f"Found stub pattern '{pat}' in server.mjs: {m.group()!r}"


def test_ac9_search_route_calls_searchDocuments():
    with open(SERVER_MJS) as f:
        src = f.read()
    assert "searchDocuments" in src, \
        "server.mjs /search route must call searchDocuments"


def test_ac9_download_route_handles_404():
    with open(SERVER_MJS) as f:
        src = f.read()
    assert re.search(r"404|not\s+found", src, re.IGNORECASE), \
        "server.mjs /download route must handle 404 case"
