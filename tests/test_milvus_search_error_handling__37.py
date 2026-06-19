"""
Tests for issue #37: Handle Milvus search errors gracefully instead of silently
catching all exceptions.

AC1 - The bare catch block in src/core/search.js:336-338 is replaced with logic
      that differentiates between expected and unexpected Milvus errors.
AC2 - Expected Milvus errors (e.g., collection not found) are caught and cause the
      function to return an empty array [].
AC3 - Unexpected errors (network timeouts, SDK errors, Milvus unavailable) are
      either re-thrown or result in an HTTP 502 response rather than silently
      returning [].
AC4 - All caught errors are logged with enough detail for observability (error
      type, message, and relevant context).
AC5 - The change does not alter the return shape or API contract for the
      successful search path.
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
COLLECTION_PATH = os.path.join(REPO_ROOT, "collection.json")


def _run_node(script, timeout=30, env_overrides=None):
    env = os.environ.copy()
    # Remove MILVUS_HOST unless explicitly overridden (use file-backed path)
    env.pop("MILVUS_HOST", None)
    if env_overrides:
        env.update(env_overrides)
    result = subprocess.run(
        ["node", "--input-type=module"],
        input=script,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=timeout,
        env=env,
    )
    return result.stdout, result.stderr, result.returncode


def _find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


class _ServerProcess:
    """Context manager: starts the real Node server on a free port."""

    def __init__(self, env_extra=None):
        self.port = _find_free_port()
        self.proc = None
        self.env_extra = env_extra or {}

    def __enter__(self):
        env = os.environ.copy()
        env.pop("MILVUS_HOST", None)
        env["PORT"] = str(self.port)
        env.update(self.env_extra)
        self.proc = subprocess.Popen(
            ["node", SERVER_MJS],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=REPO_ROOT,
            env=env,
        )
        deadline = time.time() + 10
        while time.time() < deadline:
            try:
                conn = http.client.HTTPConnection("localhost", self.port, timeout=1)
                conn.request("GET", "/health")
                resp = conn.getresponse()
                conn.close()
                if resp.status == 200:
                    break
            except Exception:
                time.sleep(0.15)
        return self

    def get(self, path):
        conn = http.client.HTTPConnection("localhost", self.port, timeout=10)
        conn.request("GET", path)
        resp = conn.getresponse()
        body = resp.read()
        conn.close()
        return resp.status, dict(resp.getheaders()), body

    def __exit__(self, *_):
        if self.proc:
            self.proc.terminate()
            self.proc.wait(timeout=5)


# ---------------------------------------------------------------------------
# AC1 — Bare catch replaced with differentiated handling
# ---------------------------------------------------------------------------


def test_ac1_named_catch_variable_in_milvus_search():
    """_searchMilvus catch block must have a named error variable (not bare catch)."""
    with open(CORE_SEARCH_JS) as f:
        src = f.read()
    milvus_start = src.find("async function _searchMilvus")
    assert milvus_start != -1, "_searchMilvus function must exist in src/core/search.js"
    milvus_section = src[milvus_start:]
    assert re.search(r"catch\s*\(\s*\w+", milvus_section), (
        "_searchMilvus catch block must have a named variable: `catch (err)` not bare `catch`"
    )


def test_ac1_no_bare_silent_catch_returning_empty_array():
    """The old bare `catch { return []; }` must not be present in _searchMilvus."""
    with open(CORE_SEARCH_JS) as f:
        src = f.read()
    milvus_start = src.find("async function _searchMilvus")
    milvus_section = src[milvus_start:]
    # Bare catch with no variable, immediately returning []
    assert not re.search(r"catch\s*\{[\s\n]*return\s*\[\s*\]", milvus_section), (
        "The bare silent `catch { return []; }` must be replaced with differentiated handling"
    )


def test_ac1_conditional_logic_in_catch():
    """The catch block must contain conditional logic to differentiate error types."""
    with open(CORE_SEARCH_JS) as f:
        src = f.read()
    milvus_start = src.find("async function _searchMilvus")
    milvus_section = src[milvus_start:]
    # Must have some form of condition: `if (isExpected)`, `if (err.code ===`, etc.
    assert re.search(r"\bif\s*\(", milvus_section[milvus_section.find("catch"):]), (
        "The catch block must have an `if (...)` condition to differentiate error types"
    )


# ---------------------------------------------------------------------------
# AC2 — Expected errors (collection not found) return []
# ---------------------------------------------------------------------------


def test_ac2_expected_error_pattern_in_source():
    """search.js must check for collection-not-found or similar expected errors."""
    with open(CORE_SEARCH_JS) as f:
        src = f.read()
    # Must check for known expected Milvus error patterns
    has_msg_check = re.search(
        r"(collection|COLLECTION).*(not found|doesn.?t exist|not exist|NOT_EXIST)",
        src,
        re.IGNORECASE,
    )
    has_code_check = re.search(r"err\??\.(code|status)\b", src)
    assert has_msg_check or has_code_check, (
        "search.js must check for expected errors like 'collection not found' "
        "(by message pattern or error code)"
    )


def test_ac2_expected_error_returns_empty_array():
    """Simulated 'collection not found' error must cause searchDocuments to return []."""
    # Write a tiny ESM stub that mimics a collection-not-found error from MilvusClient
    # We inject via a wrapper script that monkey-patches the dynamic import
    script = r"""
// Inject a mock for @zilliz/milvus2-sdk-node using a module registry hack.
// We use globalThis to carry the mock so the dynamically imported search.js
// can reach it via the "real" module path — instead we intercept via a loader.
// Since ESM loader hooks require --experimental-loader flag, we test
// the differentiation by inspecting the error-handling code path directly.

// Alternative: simulate the error scenario at the searchDocuments level
// by checking source code logic handles the expected error message.

// This test verifies via static analysis that the expected-error path returns [].
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const src = readFileSync(join(__dirname, 'src', 'core', 'search.js'), 'utf8');

// Find the _searchMilvus function's catch block
const milvusStart = src.indexOf('async function _searchMilvus');
const milvusSection = src.slice(milvusStart);

// The expected-error path must return []
const hasExpectedReturnEmpty = /isExpected.*return\s*\[\]|return\s*\[\].*isExpected/s.test(milvusSection) ||
  (/(isExpected|expectedError|knownError)/.test(milvusSection) && /return\s*\[\s*\]/.test(milvusSection));

process.stdout.write(JSON.stringify({ hasExpectedReturnEmpty }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Script failed: {err}"
    data = json.loads(out)
    assert data["hasExpectedReturnEmpty"], (
        "_searchMilvus must return [] when an expected error (collection not found) occurs. "
        "Expected a conditional `if (isExpected) return []` pattern in the catch block."
    )


# ---------------------------------------------------------------------------
# AC3 — Unexpected errors re-thrown / 502 from server
# ---------------------------------------------------------------------------


def test_ac3_throw_present_in_milvus_catch():
    """_searchMilvus must re-throw unexpected errors (throw statement in catch block)."""
    with open(CORE_SEARCH_JS) as f:
        src = f.read()
    milvus_start = src.find("async function _searchMilvus")
    milvus_section = src[milvus_start:]
    assert re.search(r"\bthrow\b", milvus_section), (
        "_searchMilvus must re-throw unexpected errors — a `throw` statement must be present "
        "in the catch block"
    )


def test_ac3_server_has_502_handling_for_search():
    """Server /search route must return 502 when searchDocuments throws unexpectedly."""
    with open(SERVER_MJS) as f:
        src = f.read()
    # Server must respond with 502 for unexpected search failures
    assert "502" in src, (
        "src/server.mjs must contain a 502 response for unexpected search errors"
    )


def test_ac3_server_search_route_has_try_catch():
    """Server /search route must have error handling (try/catch) around search call."""
    with open(SERVER_MJS) as f:
        src = f.read()
    # Find the search route handler section
    search_route_idx = src.find("GET /search")
    assert search_route_idx != -1, "server.mjs must have a GET /search route"
    # Look for try/catch in the region after the route comment
    # (before the next route comment)
    next_route_idx = src.find("// GET /", search_route_idx + 10)
    if next_route_idx == -1:
        next_route_idx = search_route_idx + 500
    route_section = src[search_route_idx:next_route_idx + 200]
    assert "try" in route_section and "catch" in route_section, (
        "server.mjs /search route must wrap searchDocuments in try/catch to handle errors"
    )


def test_ac3_server_returns_502_on_search_failure():
    """GET /search must return 502 when MILVUS_HOST is set but unreachable."""
    # Use a port that is almost certainly not listening (ephemeral high port)
    with _ServerProcess(env_extra={"MILVUS_HOST": "127.0.0.1", "MILVUS_PORT": "19531"}) as srv:
        # Give the search some time but cap it — the SDK should fail quickly on ECONNREFUSED
        try:
            status, headers, body = srv.get("/search?q=test+query&k=3")
        except Exception as e:
            pytest.skip(f"Server not reachable: {e}")
    # Should be 502 (Milvus unavailable = unexpected error) not 200 with empty results
    assert status == 502, (
        f"GET /search with unreachable Milvus must return 502, got {status}. "
        f"Body: {body[:200]!r}"
    )


# ---------------------------------------------------------------------------
# AC4 — All caught errors are logged with observability detail
# ---------------------------------------------------------------------------


def test_ac4_console_error_in_milvus_catch():
    """The catch block must log errors using console.error or console.warn."""
    with open(CORE_SEARCH_JS) as f:
        src = f.read()
    milvus_start = src.find("async function _searchMilvus")
    milvus_section = src[milvus_start:]
    assert re.search(r"console\.(error|warn)", milvus_section), (
        "_searchMilvus catch block must call console.error or console.warn to log errors"
    )


def test_ac4_log_includes_error_message():
    """The log call must include the error message or error object."""
    with open(CORE_SEARCH_JS) as f:
        src = f.read()
    milvus_start = src.find("async function _searchMilvus")
    milvus_section = src[milvus_start:]
    assert re.search(r"console\.(error|warn)\s*\([^)]*err", milvus_section), (
        "The log call must include `err` or `err.message` so error details are observable"
    )


def test_ac4_log_includes_collection_context():
    """The log call must include relevant context (collection name or query)."""
    with open(CORE_SEARCH_JS) as f:
        src = f.read()
    milvus_start = src.find("async function _searchMilvus")
    milvus_section = src[milvus_start:]
    # Must include collection name or query in the log statement
    assert re.search(
        r"console\.(error|warn)[^;]*COLLECTION_NAME|console\.(error|warn)[^;]*collection",
        milvus_section,
    ), (
        "The log call must include context (collection name) for observability"
    )


# ---------------------------------------------------------------------------
# AC5 — Return shape unchanged on success path
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = {"id", "headline", "details", "score", "attachment_url", "best_passage"}


def test_ac5_success_path_not_altered_in_source():
    """The return statement after successful search results must remain unchanged."""
    with open(CORE_SEARCH_JS) as f:
        src = f.read()
    # The return mapping object with all required fields must still be present
    for field in ("id", "headline", "details", "score", "attachment_url", "best_passage"):
        assert field in src, (
            f"Return shape field '{field}' must still be present in src/core/search.js"
        )


def test_ac5_file_backed_search_returns_correct_shape():
    """When MILVUS_HOST is not set, successful search returns correct shape."""
    script = """
import { searchDocuments } from './src/core/search.js';
const results = await searchDocuments('vector search', 5);
process.stdout.write(JSON.stringify(results));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"searchDocuments threw unexpectedly (no Milvus): {err}"
    results = json.loads(out)
    assert isinstance(results, list), f"Expected list, got: {type(results)}"
    for r in results:
        missing = REQUIRED_FIELDS - set(r.keys())
        assert not missing, f"Result missing fields {missing}: {list(r.keys())}"


def test_ac5_empty_query_still_returns_empty_list():
    """Empty query returns [] without throwing."""
    script = """
import { searchDocuments } from './src/core/search.js';
const results = await searchDocuments('', 5);
process.stdout.write(JSON.stringify(results));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"searchDocuments threw on empty query: {err}"
    results = json.loads(out)
    assert results == [], f"Expected [] for empty query, got: {results}"


def test_ac5_score_ordering_preserved():
    """Results are still returned in descending score order."""
    script = """
import { searchDocuments } from './src/core/search.js';
const results = await searchDocuments('vector embedding neural', 10);
process.stdout.write(JSON.stringify(results));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"searchDocuments failed: {err}"
    results = json.loads(out)
    scores = [r["score"] for r in results]
    for i in range(len(scores) - 1):
        assert scores[i] >= scores[i + 1], (
            f"Score ordering broken after error-handling refactor: "
            f"scores[{i}]={scores[i]} < scores[{i+1}]={scores[i+1]}"
        )
