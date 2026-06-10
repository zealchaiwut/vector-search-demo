"""
Acceptance tests for issue #9: recall@k evaluation script.

AC1  - Script lives at src/eval/ and wired to npm run eval in package.json
AC2  - Sample query set hardcoded (min 5 queries), each with expected doc_id(s)
AC3  - Script runs search against live ingested collection (no mocking in prod)
AC4  - Per-query output: query text, expected doc_id(s), hit/miss label
AC5  - Overall recall@k printed at end
AC6  - k and pass threshold configurable (env vars or config block)
AC7  - Exit 0 when recall >= threshold, non-zero otherwise
AC8  - CI can run npm run eval and rely on exit code as quality gate
"""

import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------------------
# Mock search HTTP server helpers
# ---------------------------------------------------------------------------

class _MockSearchHandler(BaseHTTPRequestHandler):
    results_factory = None  # callable(body) -> list[dict]

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}
        results = self.__class__.results_factory(body) if self.__class__.results_factory else []
        payload = json.dumps({"results": results}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_):
        pass


def _start_mock_server(port, results_factory):
    _MockSearchHandler.results_factory = results_factory
    srv = HTTPServer(("localhost", port), _MockSearchHandler)
    t = threading.Thread(target=srv.serve_forever)
    t.daemon = True
    t.start()
    return srv


def _run_eval(extra_env=None):
    env = {**os.environ, "CI": "1"}
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["npm", "run", "eval", "--silent"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )


# ---------------------------------------------------------------------------
# AC1 — script location and npm wiring
# ---------------------------------------------------------------------------

def test_ac1_script_file_exists():
    """src/eval/ must contain an entry-point file."""
    eval_dir = os.path.join(REPO_ROOT, "src", "eval")
    files = os.listdir(eval_dir) if os.path.isdir(eval_dir) else []
    has_entry = any(f in files for f in ("index.js", "index.ts", "index.mjs"))
    assert has_entry, "src/eval/ must contain index.js, index.ts, or index.mjs"


def test_ac1_package_json_has_eval_script():
    """package.json must declare an 'eval' script."""
    pkg_path = os.path.join(REPO_ROOT, "package.json")
    assert os.path.exists(pkg_path), "package.json missing"
    with open(pkg_path) as f:
        pkg = json.load(f)
    assert "eval" in pkg.get("scripts", {}), "package.json scripts.eval is missing"


# ---------------------------------------------------------------------------
# AC2 — hardcoded query set with >= 5 queries
# ---------------------------------------------------------------------------

def test_ac2_minimum_five_queries():
    """The script must embed at least 5 hardcoded queries with expected doc_ids."""
    # Parse the source for query entries — look for patterns like { query: "..." }
    # This is a structural check: count objects in the QUERIES array.
    for fname in ("index.js", "index.ts", "index.mjs"):
        fpath = os.path.join(REPO_ROOT, "src", "eval", fname)
        if os.path.exists(fpath):
            with open(fpath) as f:
                source = f.read()
            # Count occurrences of the query key in the hardcoded list
            query_count = source.count('"query"') + source.count("'query'") + source.count("`query`")
            assert query_count >= 5, f"Expected at least 5 query entries, found {query_count}"
            return
    pytest.fail("No eval entry-point found in src/eval/")


# ---------------------------------------------------------------------------
# AC4 — per-query output format (with all-miss mock)
# ---------------------------------------------------------------------------

def test_ac4_per_query_hit_miss_label():
    """Each query line must include MISS or HIT label."""
    port = 19401
    srv = _start_mock_server(port, lambda _body: [])
    try:
        result = _run_eval({
            "SEARCH_URL": f"http://localhost:{port}/search",
            "K": "5",
            "RECALL_THRESHOLD": "0.0",  # pass even with 0 recall so we see output
        })
        out = result.stdout + result.stderr
        assert "MISS" in out or "HIT" in out, f"Expected HIT/MISS in output, got:\n{out}"
    finally:
        srv.shutdown()


def test_ac4_per_query_shows_expected_docids():
    """Each query line must mention the expected doc_id(s)."""
    port = 19402
    srv = _start_mock_server(port, lambda _body: [])
    try:
        result = _run_eval({
            "SEARCH_URL": f"http://localhost:{port}/search",
            "RECALL_THRESHOLD": "0.0",
        })
        out = result.stdout + result.stderr
        # At least one article-id pattern should appear in output
        assert "article" in out.lower() or "expected" in out.lower(), \
            f"Expected article ID reference in output, got:\n{out}"
    finally:
        srv.shutdown()


# ---------------------------------------------------------------------------
# AC5 — overall recall@k line at the end
# ---------------------------------------------------------------------------

def test_ac5_recall_summary_line():
    """Output must end with a Recall@k summary line."""
    port = 19501
    srv = _start_mock_server(port, lambda _body: [])
    try:
        result = _run_eval({
            "SEARCH_URL": f"http://localhost:{port}/search",
            "RECALL_THRESHOLD": "0.0",
            "K": "5",
        })
        out = result.stdout + result.stderr
        assert "Recall@5" in out or "recall@5" in out or "RECALL@5" in out, \
            f"Expected Recall@5 summary line, got:\n{out}"
        assert "/" in out, "Expected fraction like '(4/5 queries passed)' in output"
    finally:
        srv.shutdown()


# ---------------------------------------------------------------------------
# AC6 — K and RECALL_THRESHOLD are configurable
# ---------------------------------------------------------------------------

def test_ac6_k_configurable():
    """K env var must change the k used in the recall summary."""
    port = 19601
    srv = _start_mock_server(port, lambda _body: [])
    try:
        result = _run_eval({
            "SEARCH_URL": f"http://localhost:{port}/search",
            "K": "3",
            "RECALL_THRESHOLD": "0.0",
        })
        out = result.stdout + result.stderr
        assert "Recall@3" in out or "recall@3" in out or "RECALL@3" in out, \
            f"Expected Recall@3 when K=3, got:\n{out}"
    finally:
        srv.shutdown()


def test_ac6_threshold_configurable_causes_pass():
    """RECALL_THRESHOLD=0.0 must make script exit 0 even with all misses."""
    port = 19602
    srv = _start_mock_server(port, lambda _body: [])
    try:
        result = _run_eval({
            "SEARCH_URL": f"http://localhost:{port}/search",
            "RECALL_THRESHOLD": "0.0",
        })
        assert result.returncode == 0, \
            f"Expected exit 0 with threshold=0.0, got {result.returncode}\n{result.stdout}\n{result.stderr}"
    finally:
        srv.shutdown()


# ---------------------------------------------------------------------------
# AC7 — exit codes
# ---------------------------------------------------------------------------

def test_ac7_exit_0_when_recall_meets_threshold():
    """Exit 0 when all queries hit and threshold is met."""
    port = 19701
    # Return the expected doc id for every query
    # We can't know them without parsing source, so return a rich result set
    # The eval script will treat any result.id matching expected[] as a hit.
    # To guarantee all hits we return a list that includes many possible IDs.
    hits_payload = [{"id": f"article-{i:03d}", "score": 0.9} for i in range(1, 20)]
    srv = _start_mock_server(port, lambda _body: hits_payload)
    try:
        result = _run_eval({
            "SEARCH_URL": f"http://localhost:{port}/search",
            "RECALL_THRESHOLD": "1.0",
            "K": "20",
        })
        assert result.returncode == 0, \
            f"Expected exit 0 when all queries hit, got {result.returncode}\n{result.stdout}\n{result.stderr}"
    finally:
        srv.shutdown()


def test_ac7_exit_nonzero_when_below_threshold():
    """Exit non-zero when recall < threshold."""
    port = 19702
    srv = _start_mock_server(port, lambda _body: [])  # all misses
    try:
        result = _run_eval({
            "SEARCH_URL": f"http://localhost:{port}/search",
            "RECALL_THRESHOLD": "1.0",  # impossible to meet with 0 hits
        })
        assert result.returncode != 0, \
            f"Expected non-zero exit with threshold=1.0 and no hits, got {result.returncode}"
    finally:
        srv.shutdown()


def test_ac7_exit_nonzero_empty_collection():
    """UAT Step 5: empty collection → recall=0 → exit non-zero, no crash."""
    port = 19703
    srv = _start_mock_server(port, lambda _body: [])
    try:
        result = _run_eval({
            "SEARCH_URL": f"http://localhost:{port}/search",
            "RECALL_THRESHOLD": "0.8",
        })
        out = result.stdout + result.stderr
        assert result.returncode != 0, "Expected non-zero exit with empty collection"
        assert "Recall@" in out or "recall@" in out, "Summary line must appear even with 0 recall"
        # Must not raise an unhandled exception / empty output
        assert len(out.strip()) > 0, "Output must not be empty"
    finally:
        srv.shutdown()


# ---------------------------------------------------------------------------
# AC8 — CI quality gate (exit code is deterministic and reliable)
# ---------------------------------------------------------------------------

def test_ac8_threshold_above_actual_recall_fails():
    """RECALL_THRESHOLD above current recall triggers non-zero exit."""
    port = 19801
    srv = _start_mock_server(port, lambda _body: [])
    try:
        result = _run_eval({
            "SEARCH_URL": f"http://localhost:{port}/search",
            "RECALL_THRESHOLD": "1.0",
        })
        assert result.returncode != 0
    finally:
        srv.shutdown()


def test_ac8_repeated_run_deterministic():
    """Two identical runs produce the same exit code (no randomness)."""
    port = 19802
    srv = _start_mock_server(port, lambda _body: [])
    try:
        env = {
            "SEARCH_URL": f"http://localhost:{port}/search",
            "RECALL_THRESHOLD": "0.0",
        }
        r1 = _run_eval(env)
        r2 = _run_eval(env)
        assert r1.returncode == r2.returncode, \
            "Exit code must be deterministic across repeated runs"
    finally:
        srv.shutdown()
