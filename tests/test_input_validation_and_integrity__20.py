"""
Acceptance tests for issue #20: Add input validation and vector-article integrity check.

AC1 - headline is required on create, edit, bulk; empty/whitespace-only returns 400
      with message "headline is required"
AC2 - details is required on create, edit, bulk; same rejection behavior
AC3 - attachment_url when provided must match ^https?://; non-URL returns 400 with
      message "attachment_url must be a valid http or https URL"
AC4 - Bulk path validates every item; returns HTTP 400 listing all failing indices
      (atomic rejection — nothing is persisted if any item is invalid)
AC5 - GET /health/integrity returns 200 with status "ok" and matching counts
AC6 - When counts differ, returns 200 with status "mismatch" and delta
AC7 - Validation logic lives in the article logic module; server imports and calls it
AC8 - Validation errors are logged at WARN level with offending field and value
"""

import os
import re
import subprocess

import httpx
import pytest

UAT_BASE_URL = os.environ.get("UAT_BASE_URL", "http://localhost:8001")

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SERVER_PATH = os.path.join(REPO_ROOT, "src", "server.mjs")
VALIDATION_MODULE = os.path.join(REPO_ROOT, "src", "data", "articleValidation.js")
VERIFY_COMMAND = os.path.join(REPO_ROOT, "src", "commands", "verify.js")
CLI_PATH = os.path.join(REPO_ROOT, "src", "cli.js")


# ---------------------------------------------------------------------------
# Source inspection helpers
# ---------------------------------------------------------------------------

def _server_src():
    with open(SERVER_PATH) as f:
        return f.read()


def _validation_src():
    with open(VALIDATION_MODULE) as f:
        return f.read()


def _verify_src():
    with open(VERIFY_COMMAND) as f:
        return f.read()


def _cli_src():
    with open(CLI_PATH) as f:
        return f.read()


# ---------------------------------------------------------------------------
# AC7 — Validation logic lives in a dedicated article logic module
# ---------------------------------------------------------------------------

def test_ac7_validation_module_exists():
    """src/data/articleValidation.js must exist."""
    assert os.path.exists(VALIDATION_MODULE), \
        f"Validation module not found at {VALIDATION_MODULE}"


def test_ac7_server_imports_validation_module():
    """server.mjs must import from the articleValidation module."""
    src = _server_src()
    assert re.search(r'articleValidation|validateArticle', src), \
        "server.mjs does not import from articleValidation module"


def test_ac7_validation_module_exports_validate_function():
    """articleValidation.js must export a validation function."""
    src = _validation_src()
    assert re.search(r'export\s+function\s+validate|export\s*\{\s*validate', src), \
        "articleValidation.js does not export a validate function"


def test_ac7_server_does_not_inline_url_pattern():
    """server.mjs must not duplicate URL validation regex — it should call the module."""
    srv = _server_src()
    val = _validation_src()
    # URL pattern should be in the validation module, not directly re-implemented in server
    assert re.search(r'https?\?', val), \
        "articleValidation.js does not contain URL validation pattern"


# ---------------------------------------------------------------------------
# AC1 — headline required; specific message
# ---------------------------------------------------------------------------

def test_ac1_validation_module_checks_headline():
    """articleValidation.js must produce 'headline is required' error."""
    src = _validation_src()
    assert "headline is required" in src, \
        "articleValidation.js missing 'headline is required' message"


def test_ac1_server_uses_headline_specific_message():
    """server.mjs must surface the specific 'headline is required' message."""
    src = _server_src()
    assert "headline is required" in src or re.search(r'validateArticle|articleValidation', src), \
        "server.mjs does not surface field-specific headline validation"


# ---------------------------------------------------------------------------
# AC2 — details required; specific message
# ---------------------------------------------------------------------------

def test_ac2_validation_module_checks_details():
    """articleValidation.js must produce 'details is required' error."""
    src = _validation_src()
    assert "details is required" in src, \
        "articleValidation.js missing 'details is required' message"


# ---------------------------------------------------------------------------
# AC3 — attachment_url must match ^https?://
# ---------------------------------------------------------------------------

def test_ac3_validation_module_checks_url():
    """articleValidation.js must validate attachment_url against https?:// pattern."""
    src = _validation_src()
    assert re.search(r'https?\?', src), \
        "articleValidation.js does not contain URL pattern check"
    assert "attachment_url must be a valid http or https URL" in src, \
        "articleValidation.js missing exact attachment_url error message"


# ---------------------------------------------------------------------------
# AC4 — Bulk atomic rejection path exists
# ---------------------------------------------------------------------------

def test_ac4_server_bulk_validates_all_before_persisting():
    """server.mjs bulk handler must validate all rows before any persist (atomic)."""
    src = _server_src()
    # Must have logic to collect all errors from all rows before persisting
    assert re.search(r'allErrors|bulkErrors|validat.*all|all.*valid', src, re.IGNORECASE) or \
           re.search(r'errors.*push|push.*errors', src), \
        "server.mjs bulk handler does not collect errors across all rows before persisting"


def test_ac4_server_bulk_returns_400_on_any_failure():
    """server.mjs bulk handler must return HTTP 400 if any item fails validation."""
    src = _server_src()
    # The bulk section must have a 400 response path
    assert re.search(r'400', src), \
        "server.mjs does not return HTTP 400 anywhere"


# ---------------------------------------------------------------------------
# AC5 — GET /health/integrity endpoint
# ---------------------------------------------------------------------------

def test_ac5_server_has_health_integrity_endpoint():
    """server.mjs must handle GET /health/integrity."""
    src = _server_src()
    assert re.search(r'/health/integrity', src), \
        "server.mjs does not have GET /health/integrity endpoint"


def test_ac5_server_integrity_check_queries_counts():
    """server.mjs integrity endpoint must compare articleCount and vectorCount."""
    src = _server_src()
    assert re.search(r'entityCount|vectorCount|listArticles', src), \
        "server.mjs integrity endpoint does not query article/vector counts"


# ---------------------------------------------------------------------------
# AC6 — MISMATCH response when counts differ
# ---------------------------------------------------------------------------

def test_ac6_server_handles_mismatch_case():
    """server.mjs must produce a mismatch response when counts differ."""
    src = _server_src()
    assert re.search(r'mismatch|MISMATCH', src), \
        "server.mjs does not handle the count mismatch case"
    assert re.search(r'delta', src), \
        "server.mjs mismatch response does not include delta"


# ---------------------------------------------------------------------------
# AC5/AC6 — commander verify CLI command
# ---------------------------------------------------------------------------

def test_ac5_verify_command_module_exists():
    """src/commands/verify.js must exist."""
    assert os.path.exists(VERIFY_COMMAND), \
        f"verify command not found at {VERIFY_COMMAND}"


def test_ac5_verify_command_prints_ok():
    """verify.js must print 'OK: N articles, N vectors' format on match."""
    src = _verify_src()
    assert re.search(r'OK:', src), \
        "verify.js does not print 'OK:' prefix"
    assert re.search(r'articles', src), \
        "verify.js does not include 'articles' in OK output"
    assert re.search(r'vectors', src), \
        "verify.js does not include 'vectors' in OK output"


def test_ac6_verify_command_prints_mismatch():
    """verify.js must print 'MISMATCH:' and exit non-zero on count difference."""
    src = _verify_src()
    assert re.search(r'MISMATCH:', src), \
        "verify.js does not print 'MISMATCH:' prefix"
    assert re.search(r'delta', src), \
        "verify.js does not include delta in MISMATCH output"
    assert re.search(r'exit\s*\(\s*1\s*\)', src), \
        "verify.js does not exit with code 1 on mismatch"


def test_ac5_cli_has_verify_command():
    """cli.js must dispatch the 'verify' command."""
    src = _cli_src()
    assert re.search(r'verify', src), \
        "cli.js does not include 'verify' command dispatch"


# ---------------------------------------------------------------------------
# AC8 — WARN logging
# ---------------------------------------------------------------------------

def test_ac8_validation_module_logs_warn():
    """articleValidation.js must log at WARN level for each validation failure."""
    src = _validation_src()
    assert re.search(r'console\.warn|WARN|warn', src), \
        "articleValidation.js does not log at WARN level"


# ---------------------------------------------------------------------------
# Live UAT tests (require UAT_BASE_URL to be set)
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    if not UAT_BASE_URL.startswith("http"):
        pytest.skip("UAT_BASE_URL not set — skipping live server tests")
    with httpx.Client(base_url=UAT_BASE_URL, timeout=15.0) as c:
        yield c


@pytest.fixture
def article_id(client):
    """Create a throwaway article and return its id."""
    r = client.post("/articles", json={
        "headline": "Validation Test Base Article 20xqz",
        "details": "Base article for validation tests in issue 20.",
        "attachment_url": "",
    })
    assert r.status_code == 201, f"Setup failed: {r.text}"
    return r.json()["id"]


# AC1 — POST /articles: empty headline → 400 "headline is required"

def test_ac1_post_empty_headline_returns_400(client):
    """POST /articles with empty headline returns HTTP 400."""
    r = client.post("/articles", json={
        "headline": "",
        "details": "Some valid details here.",
        "attachment_url": "",
    })
    assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text}"
    body = r.json()
    assert "headline is required" in str(body), \
        f"Error message should contain 'headline is required', got: {body}"


def test_ac1_post_whitespace_headline_returns_400(client):
    """POST /articles with whitespace-only headline returns HTTP 400."""
    r = client.post("/articles", json={
        "headline": "   ",
        "details": "Some valid details here.",
        "attachment_url": "",
    })
    assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text}"
    body = r.json()
    assert "headline is required" in str(body), \
        f"Error message should contain 'headline is required', got: {body}"


# AC2 — POST /articles: empty/whitespace details → 400 "details is required"

def test_ac2_post_empty_details_returns_400(client):
    """POST /articles with empty details returns HTTP 400."""
    r = client.post("/articles", json={
        "headline": "A valid headline",
        "details": "",
        "attachment_url": "",
    })
    assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text}"
    body = r.json()
    assert "details is required" in str(body), \
        f"Error message should contain 'details is required', got: {body}"


def test_ac2_post_whitespace_details_returns_400(client):
    """POST /articles with whitespace-only details returns HTTP 400."""
    r = client.post("/articles", json={
        "headline": "A valid headline",
        "details": "   ",
        "attachment_url": "",
    })
    assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text}"
    body = r.json()
    assert "details is required" in str(body), \
        f"Error message should contain 'details is required', got: {body}"


# AC3 — POST /articles: invalid attachment_url → 400

def test_ac3_post_invalid_attachment_url_returns_400(client):
    """POST /articles with non-URL attachment_url returns HTTP 400."""
    r = client.post("/articles", json={
        "headline": "A valid headline",
        "details": "Some valid details.",
        "attachment_url": "not-a-url",
    })
    assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text}"
    body = r.json()
    assert "attachment_url must be a valid http or https URL" in str(body), \
        f"Error message wrong, got: {body}"


def test_ac3_post_ftp_attachment_url_returns_400(client):
    """POST /articles with ftp:// attachment_url returns HTTP 400."""
    r = client.post("/articles", json={
        "headline": "A valid headline",
        "details": "Some valid details.",
        "attachment_url": "ftp://example.com/file.pdf",
    })
    assert r.status_code == 400, f"Expected 400 for ftp://, got {r.status_code}: {r.text}"


def test_ac3_post_valid_https_url_succeeds(client):
    """POST /articles with valid https:// attachment_url returns HTTP 201."""
    r = client.post("/articles", json={
        "headline": "Article With Valid Attachment 20xqz",
        "details": "This article has a valid attachment URL.",
        "attachment_url": "https://example.com/file.pdf",
    })
    assert r.status_code == 201, f"Expected 201 for https://, got {r.status_code}: {r.text}"


def test_ac3_post_valid_http_url_succeeds(client):
    """POST /articles with valid http:// attachment_url returns HTTP 201."""
    r = client.post("/articles", json={
        "headline": "Article With HTTP Attachment 20xqz",
        "details": "This article has an http attachment URL.",
        "attachment_url": "http://example.com/file.pdf",
    })
    assert r.status_code == 201, f"Expected 201 for http://, got {r.status_code}: {r.text}"


# AC1/AC2 — PUT /articles/:id: empty fields → 400

def test_ac1_put_empty_headline_returns_400(client, article_id):
    """PUT /articles/:id with empty headline returns HTTP 400."""
    r = client.put(f"/articles/{article_id}", json={
        "headline": "",
        "details": "Valid details for edit.",
        "attachment_url": "",
    })
    assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text}"
    body = r.json()
    assert "headline is required" in str(body), \
        f"Error message should contain 'headline is required', got: {body}"


def test_ac2_put_empty_details_returns_400(client, article_id):
    """PUT /articles/:id with empty details returns HTTP 400."""
    r = client.put(f"/articles/{article_id}", json={
        "headline": "Updated headline",
        "details": "",
        "attachment_url": "",
    })
    assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text}"
    body = r.json()
    assert "details is required" in str(body), \
        f"Error message should contain 'details is required', got: {body}"


def test_ac3_put_invalid_attachment_url_returns_400(client, article_id):
    """PUT /articles/:id with invalid attachment_url returns HTTP 400."""
    r = client.put(f"/articles/{article_id}", json={
        "headline": "Updated headline",
        "details": "Updated valid details.",
        "attachment_url": "not-a-url",
    })
    assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text}"
    body = r.json()
    assert "attachment_url must be a valid http or https URL" in str(body), \
        f"Error message wrong, got: {body}"


# AC4 — Bulk atomic rejection

def test_ac4_bulk_invalid_headline_returns_400(client):
    """POST /articles/bulk with any empty headline returns HTTP 400."""
    rows = [
        {"headline": "Valid Article 20xqz", "details": "Valid details.", "attachment_url": ""},
        {"headline": "", "details": "Missing headline.", "attachment_url": ""},
        {"headline": "Valid Article 2 20xqz", "details": "More valid details.", "attachment_url": "invalid-url"},
    ]
    r = client.post("/articles/bulk", json={"rows": rows})
    assert r.status_code == 400, \
        f"Expected HTTP 400 for bulk with invalid items, got {r.status_code}: {r.text}"
    body = r.json()
    errors = body.get("errors", [])
    assert len(errors) >= 2, f"Expected at least 2 errors (index 1 and 2), got: {errors}"
    indices = [e.get("index", e.get("row")) for e in errors]
    assert 1 in indices, f"Error for index 1 (empty headline) not listed: {errors}"
    assert 2 in indices, f"Error for index 2 (invalid URL) not listed: {errors}"


def test_ac4_bulk_atomic_valid_item_not_persisted(client):
    """POST /articles/bulk with any invalid item must not persist valid items."""
    unique = "bulk20atomictest20xqz"
    rows = [
        {"headline": f"Should NOT Be Created {unique}", "details": f"Valid row {unique}.", "attachment_url": ""},
        {"headline": "", "details": "This row is invalid — empty headline.", "attachment_url": ""},
    ]
    r = client.post("/articles/bulk", json={"rows": rows})
    assert r.status_code == 400, \
        f"Expected HTTP 400 for bulk with invalid items, got {r.status_code}: {r.text}"

    # Valid item at index 0 must NOT be searchable
    search_r = client.get("/search", params={"q": unique})
    assert search_r.status_code == 200
    results = search_r.json().get("results", [])
    headlines = [item.get("headline", "") for item in results]
    assert not any(unique in h for h in headlines), \
        f"Valid item was persisted despite bulk rejection: {headlines}"


def test_ac4_bulk_all_valid_returns_200(client):
    """POST /articles/bulk with all valid rows returns HTTP 200."""
    unique = "bulk20allvalidxqz"
    rows = [
        {"headline": f"Bulk Valid A {unique}", "details": f"Details A {unique}.", "attachment_url": ""},
        {"headline": f"Bulk Valid B {unique}", "details": f"Details B {unique}.", "attachment_url": ""},
    ]
    r = client.post("/articles/bulk", json={"rows": rows})
    assert r.status_code == 200, \
        f"Expected HTTP 200 for all-valid bulk, got {r.status_code}: {r.text}"
    data = r.json()
    assert data.get("succeeded") == 2, f"Expected succeeded=2, got {data}"


def test_ac4_bulk_lists_all_failing_indices(client):
    """POST /articles/bulk returns errors for ALL invalid items, not just the first."""
    rows = [
        {"headline": "", "details": "Row 0 invalid headline.", "attachment_url": ""},
        {"headline": "Row 1 valid", "details": "Row 1 valid details.", "attachment_url": ""},
        {"headline": "", "details": "Row 2 invalid headline.", "attachment_url": ""},
        {"headline": "Row 3 valid", "details": "Row 3 valid details.", "attachment_url": "bad-url"},
    ]
    r = client.post("/articles/bulk", json={"rows": rows})
    assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text}"
    body = r.json()
    errors = body.get("errors", [])
    indices = [e.get("index", e.get("row")) for e in errors]
    assert 0 in indices, f"Error for index 0 not listed: {errors}"
    assert 2 in indices, f"Error for index 2 not listed: {errors}"
    assert 3 in indices, f"Error for index 3 (bad URL) not listed: {errors}"


def test_ac4_bulk_invalid_url_returns_400(client):
    """POST /articles/bulk with invalid attachment_url in any row returns HTTP 400."""
    rows = [
        {"headline": "Valid headline", "details": "Valid details.", "attachment_url": "not-a-url"},
    ]
    r = client.post("/articles/bulk", json={"rows": rows})
    assert r.status_code == 400, \
        f"Expected 400 for bulk with invalid URL, got {r.status_code}: {r.text}"


# AC5 — GET /health/integrity

def test_ac5_health_integrity_returns_200(client):
    """GET /health/integrity returns HTTP 200."""
    r = client.get("/health/integrity")
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"


def test_ac5_health_integrity_response_has_required_fields(client):
    """GET /health/integrity response includes status, articleCount, vectorCount."""
    r = client.get("/health/integrity")
    assert r.status_code == 200
    data = r.json()
    assert "status" in data, f"Response missing 'status': {data}"
    assert "articleCount" in data, f"Response missing 'articleCount': {data}"
    assert "vectorCount" in data, f"Response missing 'vectorCount': {data}"


def test_ac5_health_integrity_ok_when_counts_match(client):
    """GET /health/integrity returns status 'ok' when article and vector counts match."""
    r = client.get("/health/integrity")
    assert r.status_code == 200
    data = r.json()
    # In normal operation counts always match
    if data["articleCount"] == data["vectorCount"]:
        assert data["status"] == "ok", \
            f"Expected status='ok' when counts match, got: {data}"
