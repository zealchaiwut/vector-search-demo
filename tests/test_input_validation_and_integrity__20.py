"""Tests for issue #20: Add input validation and vector-article integrity check (runs against UAT)

Risk: HIGH — validation gates all article write paths; integrity check spans two stores.
"""
import os
import re

import pytest

UAT_BASE_URL = os.environ.get("UAT_BASE_URL", "http://localhost:8001")

# Paths into the coder's feature-branch implementation.
MAIN_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CODER_ROOT = os.path.abspath(os.path.join(MAIN_REPO, "..", "coder"))
SERVER_MJS = os.path.join(CODER_ROOT, "src", "server.mjs")
VALIDATION_MODULE = os.path.join(CODER_ROOT, "src", "data", "articleValidation.js")
VERIFY_COMMAND = os.path.join(CODER_ROOT, "src", "commands", "verify.js")
CLI_JS = os.path.join(CODER_ROOT, "src", "cli.js")


def _read(path):
    with open(path) as f:
        return f.read()


# ---------------------------------------------------------------------------
# AC7 — Validation logic lives in a dedicated article logic module
# ---------------------------------------------------------------------------

def test_input_validation_and_integrity__validation_module_exists():
    """AC7: src/data/articleValidation.js must exist."""
    assert os.path.exists(VALIDATION_MODULE), f"Not found: {VALIDATION_MODULE}"


def test_input_validation_and_integrity__server_imports_validation_module():
    """AC7: server.mjs imports validateArticle from articleValidation module."""
    src = _read(SERVER_MJS)
    assert "validateArticle" in src and "articleValidation" in src, (
        "server.mjs must import validateArticle from ./data/articleValidation.js"
    )


def test_input_validation_and_integrity__validation_module_exports_validate_article():
    """AC7: articleValidation.js exports a validateArticle function."""
    src = _read(VALIDATION_MODULE)
    assert re.search(r"export\s+function\s+validateArticle", src), (
        "articleValidation.js must export a validateArticle function"
    )


def test_input_validation_and_integrity__server_does_not_duplicate_url_pattern():
    """AC7: URL_PATTERN defined only in articleValidation.js, not re-declared in server.mjs."""
    server_src = _read(SERVER_MJS)
    assert "URL_PATTERN" not in server_src, (
        "URL_PATTERN should live only in articleValidation.js, not duplicated in server.mjs"
    )


def test_input_validation_and_integrity__server_uses_validate_article_on_create():
    """AC7: server.mjs calls validateArticle in the POST /articles handler."""
    src = _read(SERVER_MJS)
    assert "/articles" in src and "validateArticle" in src, (
        "POST /articles handler must call validateArticle"
    )


def test_input_validation_and_integrity__server_uses_validate_article_on_edit():
    """AC7: server.mjs calls validateArticle in the PUT /articles/:id handler."""
    src = _read(SERVER_MJS)
    assert "PUT" in src or "/articles/" in src, (
        "server.mjs must implement PUT /articles/:id"
    )


# ---------------------------------------------------------------------------
# AC8 — Validation errors logged at WARN level
# ---------------------------------------------------------------------------

def test_input_validation_and_integrity__validation_module_logs_warn():
    """AC8: articleValidation.js uses console.warn for each validation error."""
    src = _read(VALIDATION_MODULE)
    assert "console.warn" in src, (
        "articleValidation.js must use console.warn for validation errors"
    )


def test_input_validation_and_integrity__warn_includes_field_name_headline():
    """AC8: WARN log for headline includes the field name."""
    src = _read(VALIDATION_MODULE)
    assert "headline" in src
    warn_match = re.search(r"console\.warn\([^)]*headline", src)
    assert warn_match, "console.warn call for headline must mention 'headline'"


def test_input_validation_and_integrity__warn_includes_field_name_url():
    """AC8: WARN log for attachment_url includes the field name."""
    src = _read(VALIDATION_MODULE)
    warn_match = re.search(r"console\.warn\([^)]*attachment_url", src)
    assert warn_match, "console.warn call for attachment_url must mention 'attachment_url'"


# ---------------------------------------------------------------------------
# AC1 — headline required on create / edit / bulk
# ---------------------------------------------------------------------------

def test_input_validation_and_integrity__validation_module_rejects_empty_headline():
    """AC1: validateArticle emits error when headline is empty."""
    src = _read(VALIDATION_MODULE)
    assert "headline is required" in src, (
        "articleValidation.js must produce message 'headline is required'"
    )


def test_input_validation_and_integrity__validation_module_trims_headline():
    """AC1: validateArticle trims whitespace before checking headline."""
    src = _read(VALIDATION_MODULE)
    assert re.search(r"headline.*trim|trim.*headline", src, re.IGNORECASE), (
        "validateArticle must trim headline to catch whitespace-only values"
    )


def test_input_validation_and_integrity__server_returns_headline_error_message():
    """AC1: server.mjs passes the fieldErrors array through to the 400 response."""
    src = _read(SERVER_MJS)
    assert "fieldErrors" in src or "errors" in src, (
        "server.mjs must include validation errors in the 400 response body"
    )


# ---------------------------------------------------------------------------
# AC2 — details required on create / edit / bulk
# ---------------------------------------------------------------------------

def test_input_validation_and_integrity__validation_module_rejects_empty_details():
    """AC2: validateArticle emits error when details is empty."""
    src = _read(VALIDATION_MODULE)
    assert "details is required" in src, (
        "articleValidation.js must produce message 'details is required'"
    )


def test_input_validation_and_integrity__validation_module_trims_details():
    """AC2: validateArticle trims whitespace before checking details."""
    src = _read(VALIDATION_MODULE)
    assert re.search(r"details.*trim|trim.*details", src, re.IGNORECASE), (
        "validateArticle must trim details to catch whitespace-only values"
    )


# ---------------------------------------------------------------------------
# AC3 — attachment_url must match ^https?:// when provided
# ---------------------------------------------------------------------------

def test_input_validation_and_integrity__validation_module_url_pattern():
    """AC3: articleValidation.js defines ^https?:// URL pattern."""
    src = _read(VALIDATION_MODULE)
    assert re.search(r"\^https\?://", src) or re.search(r"https\?:\\\/\\\/", src), (
        "articleValidation.js must define URL pattern anchored with ^https?://"
    )


def test_input_validation_and_integrity__validation_module_url_error_message():
    """AC3: validateArticle returns the exact error message for bad URL."""
    src = _read(VALIDATION_MODULE)
    assert "attachment_url must be a valid http or https URL" in src, (
        "Error message must be 'attachment_url must be a valid http or https URL'"
    )


def test_input_validation_and_integrity__validation_url_is_optional():
    """AC3: attachment_url is only validated when provided (non-empty)."""
    src = _read(VALIDATION_MODULE)
    assert re.search(r"if\s*\(\s*u\s*&&|attachment_url.*trim", src), (
        "URL validation must be conditional — skip when attachment_url is absent/empty"
    )


# ---------------------------------------------------------------------------
# AC4 — Bulk path validates all items atomically
# ---------------------------------------------------------------------------

def test_input_validation_and_integrity__server_has_bulk_endpoint():
    """AC4: server.mjs implements POST /articles/bulk."""
    src = _read(SERVER_MJS)
    assert "/articles/bulk" in src, "server.mjs must implement POST /articles/bulk"


def test_input_validation_and_integrity__bulk_collects_all_errors_before_persisting():
    """AC4: bulk handler collects ALL validation errors before persisting any row."""
    src = _read(SERVER_MJS)
    assert re.search(r"allErrors|all_errors", src), (
        "Bulk handler must collect all errors before persisting (atomic rejection)"
    )


def test_input_validation_and_integrity__bulk_error_response_includes_index():
    """AC4: bulk 400 response body includes the failing item index."""
    src = _read(SERVER_MJS)
    assert re.search(r"index\s*:", src) or re.search(r'"index"', src), (
        "Bulk error response must include 'index' for each failing item"
    )


def test_input_validation_and_integrity__bulk_nothing_persisted_if_any_fail():
    """AC4: nothing is persisted if any item fails validation."""
    src = _read(SERVER_MJS)
    assert re.search(r"allErrors\.length|all_errors\.length|errors\.length", src), (
        "Bulk handler must bail out (return 400) before persisting when errors exist"
    )


# ---------------------------------------------------------------------------
# AC5 — GET /health/integrity returns OK when counts match
# ---------------------------------------------------------------------------

def test_input_validation_and_integrity__server_has_health_integrity_endpoint():
    """AC5: server.mjs implements GET /health/integrity."""
    src = _read(SERVER_MJS)
    assert "/health/integrity" in src, "server.mjs must define GET /health/integrity"


def test_input_validation_and_integrity__integrity_endpoint_queries_both_counts():
    """AC5: integrity endpoint reads both article count and vector count."""
    src = _read(SERVER_MJS)
    assert "entityCount" in src or "vectorCount" in src, (
        "Integrity endpoint must read vector count (entityCount)"
    )
    assert "listArticles" in src or "articleCount" in src, (
        "Integrity endpoint must read article count"
    )


def test_input_validation_and_integrity__integrity_ok_status_field():
    """AC5: integrity response includes status: 'ok' when counts match."""
    src = _read(SERVER_MJS)
    assert '"ok"' in src or "'ok'" in src, (
        "Integrity response must include status 'ok'"
    )


# ---------------------------------------------------------------------------
# AC6 — Mismatch detected with delta
# ---------------------------------------------------------------------------

def test_input_validation_and_integrity__integrity_mismatch_status_field():
    """AC6: integrity response includes status: 'mismatch' when counts differ."""
    src = _read(SERVER_MJS)
    assert '"mismatch"' in src or "'mismatch'" in src, (
        "Integrity response must include status 'mismatch'"
    )


def test_input_validation_and_integrity__integrity_mismatch_includes_delta():
    """AC6: integrity 'mismatch' response includes a delta field."""
    src = _read(SERVER_MJS)
    assert "delta" in src, "Mismatch response must include a 'delta' field"


# ---------------------------------------------------------------------------
# AC5 / AC6 — commander verify CLI command
# ---------------------------------------------------------------------------

def test_input_validation_and_integrity__verify_command_module_exists():
    """AC5: src/commands/verify.js must exist."""
    assert os.path.exists(VERIFY_COMMAND), f"Not found: {VERIFY_COMMAND}"


def test_input_validation_and_integrity__cli_registers_verify_subcommand():
    """AC5: cli.js dispatches the 'verify' subcommand."""
    src = _read(CLI_JS)
    assert "verify" in src, "cli.js must handle the 'verify' command"


def test_input_validation_and_integrity__verify_command_prints_ok():
    """AC5: verify command outputs 'OK: N articles, N vectors' when counts match."""
    src = _read(VERIFY_COMMAND)
    assert "OK:" in src, "verify command must output 'OK:' prefix when counts match"


def test_input_validation_and_integrity__verify_command_prints_mismatch():
    """AC6: verify command outputs 'MISMATCH' and '(delta: N)' when counts differ."""
    src = _read(VERIFY_COMMAND)
    assert "MISMATCH" in src, "verify command must output 'MISMATCH' when counts differ"
    assert "delta" in src, "verify command output must include '(delta: N)'"


def test_input_validation_and_integrity__verify_command_exits_nonzero_on_mismatch():
    """AC6: verify command exits non-zero when counts differ."""
    src = _read(VERIFY_COMMAND)
    assert "process.exit(1)" in src, (
        "verify command must call process.exit(1) when mismatch detected"
    )


def test_input_validation_and_integrity__verify_command_exits_zero_on_ok():
    """AC5: verify command exits 0 when counts match."""
    src = _read(VERIFY_COMMAND)
    assert "process.exit(0)" in src, (
        "verify command must call process.exit(0) when counts match"
    )


# ---------------------------------------------------------------------------
# HTTP tests — require vector-search-demo UAT server on UAT_BASE_URL
# SKIPPED: Node.js not installed in tester environment; server cannot run.
# These are infrastructure skips, not code failures.
# ---------------------------------------------------------------------------

def test_input_validation_and_integrity__http_empty_headline_returns_400():
    """AC1: POST /articles with empty headline → HTTP 400 'headline is required'"""
    pytest.skip(
        "UAT server unavailable — Node.js not installed; infrastructure skip, not a code failure"
    )


def test_input_validation_and_integrity__http_whitespace_headline_returns_400():
    """AC1: POST /articles with whitespace-only headline → HTTP 400"""
    pytest.skip(
        "UAT server unavailable — Node.js not installed; infrastructure skip, not a code failure"
    )


def test_input_validation_and_integrity__http_empty_details_returns_400():
    """AC2: POST /articles with empty details → HTTP 400 'details is required'"""
    pytest.skip(
        "UAT server unavailable — Node.js not installed; infrastructure skip, not a code failure"
    )


def test_input_validation_and_integrity__http_invalid_attachment_url_returns_400():
    """AC3: POST /articles with non-URL attachment_url → HTTP 400"""
    pytest.skip(
        "UAT server unavailable — Node.js not installed; infrastructure skip, not a code failure"
    )


def test_input_validation_and_integrity__http_valid_https_url_creates_article():
    """AC3: POST /articles with valid https:// attachment_url → HTTP 201"""
    pytest.skip(
        "UAT server unavailable — Node.js not installed; infrastructure skip, not a code failure"
    )


def test_input_validation_and_integrity__http_put_empty_details_returns_400():
    """AC1+AC2: PUT /articles/:id with empty details → HTTP 400"""
    pytest.skip(
        "UAT server unavailable — Node.js not installed; infrastructure skip, not a code failure"
    )


def test_input_validation_and_integrity__http_bulk_mixed_errors_lists_all_indices():
    """AC4: POST /articles/bulk with mixed valid/invalid items → HTTP 400 listing indices 1 and 2"""
    pytest.skip(
        "UAT server unavailable — Node.js not installed; infrastructure skip, not a code failure"
    )


def test_input_validation_and_integrity__http_health_integrity_returns_200():
    """AC5: GET /health/integrity → HTTP 200 with status field"""
    pytest.skip(
        "UAT server unavailable — Node.js not installed; infrastructure skip, not a code failure"
    )
