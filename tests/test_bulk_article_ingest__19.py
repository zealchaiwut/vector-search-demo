"""
Acceptance tests for issue #19: Add bulk article ingestion via file upload.

AC1 - UI provides a file input accepting .json and .csv files; each row/entry must have
      headline, details, and attachment_url fields
AC2 - A bulk ingest endpoint accepts the parsed rows and processes each through the
      existing single-article create logic
AC3 - Each row is validated independently; an invalid row records an error and
      processing continues with remaining rows
AC4 - Response includes a progress count: total submitted, succeeded, and failed
AC5 - UI displays the final count (e.g. "8 / 10 succeeded, 2 failed") and lists
      per-row failure reasons
AC6 - All successfully ingested articles are immediately searchable
AC7 - Uploading a file of N valid rows creates exactly N articles and reports
      N succeeded, 0 failed
AC8 - Uploading a file with M invalid rows and K valid rows creates K articles,
      reports K succeeded and M failed with per-row error messages, and does not
      abort early
"""

import os
import re

import httpx
import pytest

UAT_BASE_URL = os.environ.get("UAT_BASE_URL", "http://localhost:8001")

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SERVER_PATH = os.path.join(REPO_ROOT, "src", "server.mjs")
INDEX_HTML = os.path.join(REPO_ROOT, "public", "index.html")


# ---------------------------------------------------------------------------
# Source inspection helpers
# ---------------------------------------------------------------------------

def _server_src():
    with open(SERVER_PATH) as f:
        return f.read()


def _html_src():
    with open(INDEX_HTML) as f:
        return f.read()


# ---------------------------------------------------------------------------
# Static analysis — server.mjs (AC2, AC3, AC4)
# ---------------------------------------------------------------------------

def test_ac2_server_has_bulk_endpoint():
    """server.mjs must handle POST /articles/bulk."""
    src = _server_src()
    assert re.search(r'/articles/bulk', src), \
        "No /articles/bulk endpoint found in server.mjs"


def test_ac2_server_bulk_uses_existing_create_logic():
    """server.mjs bulk handler must reuse embed + upsertRows logic."""
    src = _server_src()
    assert re.search(r'batchEmbed|embedder', src), \
        "server.mjs does not import or call the embedder"
    assert re.search(r'upsertRows|upsert', src), \
        "server.mjs does not call upsertRows"


def test_ac3_server_bulk_validates_per_row():
    """server.mjs bulk handler must validate each row independently."""
    src = _server_src()
    # Must process rows individually (loop) with per-row error recording
    assert re.search(r'for\s*(await\s*)?\(|\.forEach|\.map|\.reduce', src), \
        "server.mjs bulk handler does not iterate over rows"
    assert re.search(r'errors|failed|error', src, re.IGNORECASE), \
        "server.mjs bulk handler does not track per-row errors"


def test_ac4_server_bulk_response_has_counts():
    """server.mjs bulk endpoint response must include total, succeeded, and failed."""
    src = _server_src()
    assert "total" in src, "server.mjs bulk response missing 'total' field"
    assert "succeeded" in src, "server.mjs bulk response missing 'succeeded' field"
    assert "failed" in src, "server.mjs bulk response missing 'failed' field"


def test_ac4_server_bulk_response_has_errors_array():
    """server.mjs bulk endpoint response must include an errors array for per-row reasons."""
    src = _server_src()
    assert re.search(r'errors', src), \
        "server.mjs bulk response missing 'errors' field for per-row failure details"


# ---------------------------------------------------------------------------
# Static analysis — public/index.html (AC1, AC5)
# ---------------------------------------------------------------------------

def test_ac1_html_has_file_input():
    """index.html must contain a file input element."""
    src = _html_src()
    assert re.search(r'type\s*=\s*["\']file["\']|<input[^>]+file', src, re.IGNORECASE), \
        "No file input found in index.html"


def test_ac1_html_file_input_accepts_json_csv():
    """index.html file input must accept .json and .csv extensions."""
    src = _html_src()
    assert re.search(r'accept\s*=\s*["\'][^"\']*\.json[^"\']*["\']|accept\s*=\s*["\'][^"\']*\.csv[^"\']*["\']|accept\s*=\s*["\'][^"\']*json[^"\']*csv', src, re.IGNORECASE), \
        "File input does not specify accept='.json,.csv' (or similar) in index.html"


def test_ac5_html_displays_bulk_result_count():
    """index.html JS must display count summary after bulk upload (e.g. '8 / 10 succeeded')."""
    src = _html_src()
    assert re.search(r'succeeded|failed|total', src, re.IGNORECASE), \
        "index.html does not display succeeded/failed/total count for bulk upload"


def test_ac5_html_lists_per_row_errors():
    """index.html JS must display per-row failure reasons."""
    src = _html_src()
    assert re.search(r'errors|error.*list|failure.*reason|row.*error|per.row', src, re.IGNORECASE), \
        "index.html does not list per-row failure reasons for bulk upload"


def test_ac1_html_has_bulk_upload_section():
    """index.html must have a bulk upload section or control."""
    src = _html_src()
    has_bulk = bool(re.search(r'bulk|Bulk|import|Import|upload|Upload', src, re.IGNORECASE))
    assert has_bulk, "No bulk upload section found in index.html"


# ---------------------------------------------------------------------------
# Live UAT tests (require UAT_BASE_URL to be set)
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    if not UAT_BASE_URL.startswith("http"):
        pytest.skip("UAT_BASE_URL not set — skipping live server tests")
    with httpx.Client(base_url=UAT_BASE_URL, timeout=15.0) as c:
        yield c


def test_ac7_all_valid_rows_succeed(client):
    """POST /articles/bulk with N valid rows → N succeeded, 0 failed."""
    unique = "bulktest19validxqz"
    rows = [
        {"headline": f"Bulk Article 1 {unique}", "details": f"Details for bulk article 1 {unique}.", "attachment_url": ""},
        {"headline": f"Bulk Article 2 {unique}", "details": f"Details for bulk article 2 {unique}.", "attachment_url": ""},
        {"headline": f"Bulk Article 3 {unique}", "details": f"Details for bulk article 3 {unique}.", "attachment_url": ""},
    ]

    r = client.post("/articles/bulk", json={"rows": rows})
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()

    assert data.get("total") == 3, f"Expected total=3, got {data.get('total')}"
    assert data.get("succeeded") == 3, f"Expected succeeded=3, got {data.get('succeeded')}"
    assert data.get("failed") == 0, f"Expected failed=0, got {data.get('failed')}"
    errors = data.get("errors", [])
    assert len(errors) == 0, f"Expected no errors, got {errors}"


def test_ac8_mixed_rows_partial_success(client):
    """POST /articles/bulk with M invalid + K valid rows → K succeeded, M failed, no early abort."""
    unique = "bulktest19mixedxqz"
    rows = [
        {"headline": f"Valid Bulk Article 1 {unique}", "details": f"Valid details 1 {unique}.", "attachment_url": ""},
        {"headline": "", "details": "Missing headline row.", "attachment_url": ""},  # invalid: no headline
        {"headline": f"Valid Bulk Article 2 {unique}", "details": f"Valid details 2 {unique}.", "attachment_url": ""},
        {"headline": "Missing details row", "details": "", "attachment_url": ""},    # invalid: no details
        {"headline": f"Valid Bulk Article 3 {unique}", "details": f"Valid details 3 {unique}.", "attachment_url": ""},
    ]

    r = client.post("/articles/bulk", json={"rows": rows})
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()

    assert data.get("total") == 5, f"Expected total=5, got {data.get('total')}"
    assert data.get("succeeded") == 3, f"Expected succeeded=3, got {data.get('succeeded')}"
    assert data.get("failed") == 2, f"Expected failed=2, got {data.get('failed')}"
    errors = data.get("errors", [])
    assert len(errors) == 2, f"Expected 2 error entries, got {errors}"
    # Each error must carry a row index and a reason
    for err in errors:
        assert "row" in err or "index" in err, f"Error entry missing row index: {err}"
        assert "reason" in err or "error" in err or "message" in err, f"Error entry missing reason: {err}"


def test_ac3_invalid_rows_do_not_abort_processing(client):
    """Invalid rows do not stop subsequent valid rows from being processed."""
    unique = "bulktest19noearlystopxqz"
    rows = [
        {"headline": "", "details": "First row invalid — missing headline.", "attachment_url": ""},
        {"headline": f"Should Still Be Created {unique}", "details": f"This row comes after an invalid row {unique}.", "attachment_url": ""},
    ]

    r = client.post("/articles/bulk", json={"rows": rows})
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()

    assert data.get("succeeded") == 1, f"Expected 1 succeeded, got {data.get('succeeded')}"
    assert data.get("failed") == 1, f"Expected 1 failed, got {data.get('failed')}"

    # The valid article must be searchable
    search_r = client.get("/search", params={"q": unique})
    assert search_r.status_code == 200
    results = search_r.json().get("results", [])
    headlines = [item.get("headline", "") for item in results]
    assert any(unique in h for h in headlines), \
        f"Article after invalid row not found in search. Headlines: {headlines}"


def test_ac6_bulk_articles_immediately_searchable(client):
    """All successfully ingested bulk articles are immediately searchable after the call."""
    unique = "bulktest19searchable19xqz"
    rows = [
        {"headline": f"Searchable Bulk A {unique}", "details": f"First searchable bulk article {unique}.", "attachment_url": ""},
        {"headline": f"Searchable Bulk B {unique}", "details": f"Second searchable bulk article {unique}.", "attachment_url": ""},
    ]

    r = client.post("/articles/bulk", json={"rows": rows})
    assert r.status_code == 200
    data = r.json()
    assert data.get("succeeded") == 2

    search_r = client.get("/search", params={"q": unique})
    assert search_r.status_code == 200
    results = search_r.json().get("results", [])
    assert len(results) >= 2, \
        f"Expected at least 2 search results after bulk ingest, got {len(results)}"


def test_ac4_response_has_all_count_fields(client):
    """POST /articles/bulk response must include total, succeeded, failed, and errors."""
    r = client.post("/articles/bulk", json={"rows": [
        {"headline": "Count Field Test", "details": "Testing that all count fields are present.", "attachment_url": ""}
    ]})
    assert r.status_code == 200
    data = r.json()
    for field in ("total", "succeeded", "failed", "errors"):
        assert field in data, f"Response missing '{field}' field: {data}"


def test_ac7_exact_n_articles_created(client):
    """N valid rows creates exactly N new articles (no more, no fewer)."""
    unique = "bulktest19exactnxqz"
    n = 4
    rows = [
        {"headline": f"Exact N Test {i} {unique}", "details": f"Row {i} of exact N test {unique}.", "attachment_url": ""}
        for i in range(n)
    ]

    r = client.post("/articles/bulk", json={"rows": rows})
    assert r.status_code == 200
    data = r.json()
    assert data.get("total") == n
    assert data.get("succeeded") == n
    assert data.get("failed") == 0


def test_all_invalid_rows_zero_succeeded(client):
    """When all rows are invalid, succeeded=0 and failed=N."""
    rows = [
        {"headline": "", "details": "", "attachment_url": ""},  # both missing
        {"headline": "", "details": "No headline", "attachment_url": ""},
        {"headline": "No details", "details": "", "attachment_url": ""},
    ]

    r = client.post("/articles/bulk", json={"rows": rows})
    assert r.status_code == 200
    data = r.json()
    assert data.get("succeeded") == 0, f"Expected succeeded=0, got {data.get('succeeded')}"
    assert data.get("failed") == 3, f"Expected failed=3, got {data.get('failed')}"
    assert len(data.get("errors", [])) == 3, f"Expected 3 errors, got {data.get('errors')}"


def test_empty_rows_returns_zero_counts(client):
    """POST /articles/bulk with empty rows array returns total=0, succeeded=0, failed=0."""
    r = client.post("/articles/bulk", json={"rows": []})
    assert r.status_code == 200
    data = r.json()
    assert data.get("total") == 0
    assert data.get("succeeded") == 0
    assert data.get("failed") == 0
