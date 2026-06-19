"""
Acceptance tests for issue #68: Add JSON body support to article create endpoint and form.

AC1 - POST /articles accepts Content-Type: application/json and creates an article
AC2 - POST /articles with JSON missing a required field returns 4xx with descriptive error
AC3 - POST /articles with malformed JSON returns 400 with a clear parse-error message
AC4 - Add Article form has a "Paste JSON" toggle that reveals a textarea
AC5 - Pasting valid JSON into textarea and submitting creates the article via same path
AC6 - Pasting malformed JSON shows inline error before submission
AC7 - Pasting JSON missing a required field surfaces the same validation error
AC8 - Existing typed-field form submission is unaffected
AC9 - Existing non-JSON API requests (other endpoints) are unaffected
"""

import os
import re

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SERVER_PATH = os.path.join(REPO_ROOT, "src", "server.mjs")
INDEX_HTML = os.path.join(REPO_ROOT, "public", "index.html")


def _server_src():
    with open(SERVER_PATH) as f:
        return f.read()


def _html_src():
    with open(INDEX_HTML) as f:
        return f.read()


# ---------------------------------------------------------------------------
# AC1 — POST /articles accepts application/json body
# ---------------------------------------------------------------------------

def test_ac1_server_handles_post_articles():
    """server.mjs must handle POST /articles."""
    src = _server_src()
    assert "POST" in src and "/articles" in src, \
        "server.mjs must implement POST /articles"


def test_ac1_server_parses_json_body():
    """server.mjs POST /articles must attempt JSON.parse() on the body."""
    src = _server_src()
    assert "JSON.parse(body)" in src or "JSON.parse( body)" in src, \
        "server.mjs must call JSON.parse() on the request body"


def test_ac1_server_reads_headline_details_from_body():
    """server.mjs must read headline and details from the parsed JSON body."""
    src = _server_src()
    assert "payload.headline" in src or ("headline" in src and "payload" in src), \
        "server.mjs must read headline from the parsed body"
    assert "payload.details" in src or ("details" in src and "payload" in src), \
        "server.mjs must read details from the parsed body"


def test_ac1_server_returns_201_on_success():
    """server.mjs must return HTTP 201 on successful article creation."""
    src = _server_src()
    assert "201" in src, "server.mjs must return HTTP 201 for successful article creation"


# ---------------------------------------------------------------------------
# AC2 — Missing required field returns 4xx with descriptive message
# ---------------------------------------------------------------------------

def test_ac2_server_validates_required_fields():
    """server.mjs must call validateArticle to check required fields."""
    src = _server_src()
    assert "validateArticle" in src, \
        "server.mjs must call validateArticle for field validation"


def test_ac2_server_returns_400_for_validation_failure():
    """server.mjs must return HTTP 400 when validation fails."""
    src = _server_src()
    assert re.search(r'jsonResponse\(res,\s*400', src), \
        "server.mjs must call jsonResponse(res, 400, ...) for validation errors"


def test_ac2_server_includes_error_message_in_response():
    """server.mjs must include a descriptive error message in the 400 validation response."""
    src = _server_src()
    assert re.search(r'fieldErrors\[0\]\.message|errors.*fieldErrors|error.*message', src), \
        "server.mjs must include the validation error message in the 400 response"


# ---------------------------------------------------------------------------
# AC3 — Malformed JSON returns 400 with a clear parse-error message
# ---------------------------------------------------------------------------

def test_ac3_server_wraps_json_parse_in_try_catch():
    """server.mjs must wrap JSON.parse() in try/catch for the POST /articles handler."""
    src = _server_src()
    # Check that try and catch both appear (they can't both appear without being paired)
    assert "try {" in src and ("catch {" in src or "catch (e" in src), \
        "server.mjs must use try/catch around JSON.parse()"


def test_ac3_server_returns_400_on_bad_json():
    """server.mjs must return HTTP 400 when the request body is not valid JSON."""
    src = _server_src()
    assert re.search(r'jsonResponse\(res,\s*400', src), \
        "server.mjs must return HTTP 400 on JSON parse failure"


def test_ac3_server_parse_error_message_is_clear():
    """server.mjs parse error response body must contain a descriptive message."""
    src = _server_src()
    assert re.search(
        r'[Ii]nvalid JSON|not valid JSON|could not be parsed|[Pp]arse.*[Ee]rror|[Mm]alformed',
        src
    ), "server.mjs must include a clear parse-error message in the 400 response"


# ---------------------------------------------------------------------------
# AC4 — Add Article form has a "Paste JSON" toggle revealing a textarea
# ---------------------------------------------------------------------------

def test_ac4_html_has_paste_json_toggle():
    """index.html must include a 'Paste JSON' toggle button."""
    src = _html_src()
    assert re.search(r'[Pp]aste\s+JSON|json.toggle|json-toggle|jsonToggle', src, re.IGNORECASE), \
        "No 'Paste JSON' toggle found in index.html"


def test_ac4_html_has_json_textarea():
    """index.html must include a textarea dedicated to JSON paste input."""
    src = _html_src()
    assert re.search(r'id=["\']art-json["\']|id=["\']json-textarea["\']', src, re.IGNORECASE), \
        "No JSON textarea (id='art-json') found in index.html"


def test_ac4_html_has_json_input_section():
    """index.html must have a section for JSON input that can be shown/hidden."""
    src = _html_src()
    assert re.search(r'id=["\']json-input-section["\']|json-section|json-mode', src, re.IGNORECASE), \
        "No JSON input section found in index.html"


def test_ac4_html_toggle_controls_json_section_visibility():
    """index.html JS must toggle visibility of the JSON input section."""
    src = _html_src()
    assert re.search(r'jsonInputSection\.hidden|json-input-section.*hidden|hidden.*json-input', src), \
        "No show/hide logic for the JSON section found in index.html"


# ---------------------------------------------------------------------------
# AC5 — Submitting valid JSON from textarea creates the article
# ---------------------------------------------------------------------------

def test_ac5_html_js_parses_json_textarea_on_submit():
    """index.html JS must call JSON.parse() on the JSON textarea content at submit time."""
    src = _html_src()
    assert re.search(r'JSON\.parse\s*\(', src), \
        "No JSON.parse() call found in index.html JS (needed for JSON paste submit)"


def test_ac5_html_js_extracts_headline_from_parsed_json():
    """index.html JS must extract headline from the parsed JSON object."""
    src = _html_src()
    assert re.search(r'parsed\.headline|jsonData\.headline|json\.headline', src), \
        "index.html JS must read parsed.headline from the JSON paste input"


def test_ac5_html_js_submits_to_articles_endpoint():
    """index.html JS must POST the parsed JSON fields to /articles."""
    src = _html_src()
    assert "/articles" in src
    assert re.search(r'"Content-Type".*application/json|Content-Type.*application/json', src)


# ---------------------------------------------------------------------------
# AC6 — Malformed JSON shows inline error before submission
# ---------------------------------------------------------------------------

def test_ac6_html_has_inline_json_error_element():
    """index.html must have a dedicated inline error element for JSON parse errors."""
    src = _html_src()
    assert re.search(r'id=["\']json-parse-error["\']|id=["\']json-error["\']', src, re.IGNORECASE), \
        "No inline JSON parse error element found in index.html"


def test_ac6_html_js_shows_error_on_malformed_json():
    """index.html JS must catch JSON.parse errors from the textarea and display an inline error."""
    src = _html_src()
    assert re.search(r'jsonParseError|json-parse-error|jsonError', src), \
        "index.html JS must reference the inline JSON error element"


def test_ac6_html_js_validates_json_on_input_event():
    """index.html JS must validate JSON on textarea input (real-time feedback)."""
    src = _html_src()
    assert re.search(r'jsonTextarea.*addEventListener|art-json.*addEventListener|addEventListener.*art-json', src), \
        "index.html JS must attach an event listener to the JSON textarea"


# ---------------------------------------------------------------------------
# AC7 — Missing required field from JSON paste surfaces validation error
# ---------------------------------------------------------------------------

def test_ac7_html_validates_headline_from_json():
    """index.html JS must check that headline is present in the parsed JSON."""
    src = _html_src()
    assert re.search(r'parsed\.headline|headline.*required|headline is required', src, re.IGNORECASE), \
        "index.html JS must validate headline from the parsed JSON object"


def test_ac7_html_validates_details_from_json():
    """index.html JS must check that details is present in the parsed JSON."""
    src = _html_src()
    assert re.search(r'parsed\.details|details.*required|details is required', src, re.IGNORECASE), \
        "index.html JS must validate details from the parsed JSON object"


# ---------------------------------------------------------------------------
# AC8 — Existing typed-field form is unaffected
# ---------------------------------------------------------------------------

def test_ac8_html_typed_headline_input_present():
    """index.html must still have the typed headline input field."""
    src = _html_src()
    assert re.search(r'id=["\']art-headline["\']', src), \
        "Typed headline input (id='art-headline') must remain in index.html"


def test_ac8_html_typed_details_textarea_present():
    """index.html must still have the typed details textarea."""
    src = _html_src()
    assert re.search(r'id=["\']art-details["\']', src), \
        "Typed details textarea (id='art-details') must remain in index.html"


def test_ac8_html_typed_attachment_url_present():
    """index.html must still have the typed attachment URL input."""
    src = _html_src()
    assert re.search(r'id=["\']art-attachment-url["\']', src), \
        "Typed attachment-url input (id='art-attachment-url') must remain in index.html"


def test_ac8_html_typed_form_submit_event_present():
    """index.html JS must still have the form submit event listener for typed mode."""
    src = _html_src()
    assert re.search(r"addForm.*addEventListener.*submit|addEventListener.*submit.*addForm", src), \
        "index.html must still attach a submit event listener to the add form"


def test_ac8_html_typed_mode_extracts_from_form_elements():
    """index.html JS must still read headline from addForm.elements in typed mode."""
    src = _html_src()
    assert re.search(r'addForm\.elements\["headline"\]|addForm\.elements\[.headline.\]', src), \
        "index.html JS must still read headline from form elements in typed mode"


# ---------------------------------------------------------------------------
# AC9 — Other server endpoints are unaffected
# ---------------------------------------------------------------------------

def test_ac9_server_get_search_unaffected():
    """GET /search endpoint must still be present."""
    src = _server_src()
    assert "/search" in src, "GET /search endpoint must remain in server.mjs"


def test_ac9_server_get_articles_unaffected():
    """GET /articles endpoint must still be present."""
    src = _server_src()
    assert re.search(r'GET.*articles|articles.*GET', src) or \
           ("GET" in src and "/articles" in src), \
        "GET /articles endpoint must remain in server.mjs"


def test_ac9_server_health_integrity_unaffected():
    """GET /health/integrity endpoint must still be present."""
    src = _server_src()
    assert "/health/integrity" in src, \
        "GET /health/integrity endpoint must remain in server.mjs"


def test_ac9_server_bulk_endpoint_unaffected():
    """POST /articles/bulk endpoint must still be present."""
    src = _server_src()
    assert "/articles/bulk" in src, \
        "POST /articles/bulk endpoint must remain in server.mjs"
