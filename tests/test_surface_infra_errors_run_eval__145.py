"""
Tests for issue #145: Surface infrastructure errors in run_eval.py search() helper.

AC1  Each failed search query prints a WARNING to stderr that includes the
     exception/error message. Failure cases: server unreachable (connection
     refused), HTTP 5xx status, malformed JSON response.
AC2  When ALL queries error out, the script exits non-zero regardless of
     RECALL_THRESHOLD — preventing a server-down CI run from being misread as
     genuine low recall.
"""
import json
import os
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVAL_SCRIPT = os.path.join(REPO_ROOT, "src", "eval", "run_eval.py")
EVAL_DIR = os.path.join(REPO_ROOT, "src", "eval")


def _run_eval(extra_env):
    env = {**os.environ, **extra_env}
    return subprocess.run(
        [sys.executable, EVAL_SCRIPT],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )


def _write_dataset(entries):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False)
        return f.name


_TINY_DATASET = [{"query": "ทดสอบ", "expected": ["article-thai-001"]}]
_TWO_ENTRY_DATASET = [
    {"query": "ทดสอบ", "expected": ["article-thai-001"]},
    {"query": "ค้นหา", "expected": ["article-thai-002"]},
]


def _start_server(port, status, body):
    body_bytes = body if isinstance(body, bytes) else body.encode()

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body_bytes)))
            self.end_headers()
            self.wfile.write(body_bytes)

        def log_message(self, *_):
            pass

    srv = HTTPServer(("localhost", port), _Handler)
    t = threading.Thread(target=srv.serve_forever)
    t.daemon = True
    t.start()
    return srv


# ---------------------------------------------------------------------------
# AC1 — failed queries must print WARNING to stderr with error detail
# ---------------------------------------------------------------------------

def test_ac1_http_500_prints_warning():
    """Server returns 500 → WARNING on stderr for the failed query."""
    port = 21601
    srv = _start_server(port, 500, b"Internal Server Error")
    ds = _write_dataset(_TINY_DATASET)
    try:
        r = _run_eval({"SEARCH_URL": f"http://localhost:{port}/search",
                       "K": "5", "RECALL_THRESHOLD": "0.0", "EVAL_DATASET": ds})
        assert "warning" in r.stderr.lower(), (
            f"No WARNING in stderr for HTTP 500:\n{r.stderr}"
        )
    finally:
        os.unlink(ds)
        srv.shutdown()


def test_ac1_malformed_json_prints_warning():
    """Server returns 200 with non-JSON body → WARNING on stderr."""
    port = 21602
    srv = _start_server(port, 200, b"not-json!!!{{{")
    ds = _write_dataset(_TINY_DATASET)
    try:
        r = _run_eval({"SEARCH_URL": f"http://localhost:{port}/search",
                       "K": "5", "RECALL_THRESHOLD": "0.0", "EVAL_DATASET": ds})
        assert "warning" in r.stderr.lower(), (
            f"No WARNING in stderr for malformed JSON:\n{r.stderr}"
        )
    finally:
        os.unlink(ds)
        srv.shutdown()


def test_ac1_connection_refused_prints_warning():
    """No server on target port → WARNING on stderr (connection refused)."""
    # Port 21603: intentionally no server started
    ds = _write_dataset(_TINY_DATASET)
    try:
        r = _run_eval({"SEARCH_URL": "http://localhost:21603/search",
                       "K": "5", "RECALL_THRESHOLD": "0.0", "EVAL_DATASET": ds})
        assert "warning" in r.stderr.lower(), (
            f"No WARNING in stderr for connection refused:\n{r.stderr}"
        )
    finally:
        os.unlink(ds)


def test_ac1_warning_contains_error_text():
    """WARNING line must carry the exception text, not just a bare 'WARNING:' label."""
    port = 21604
    srv = _start_server(port, 503, b"Service Unavailable")
    ds = _write_dataset(_TINY_DATASET)
    try:
        r = _run_eval({"SEARCH_URL": f"http://localhost:{port}/search",
                       "K": "5", "RECALL_THRESHOLD": "0.0", "EVAL_DATASET": ds})
        warning_lines = [ln for ln in r.stderr.splitlines() if "warning" in ln.lower()]
        assert warning_lines, f"No WARNING lines in stderr:\n{r.stderr}"
        for ln in warning_lines:
            # Must be longer than just "WARNING: " (9 chars)
            assert len(ln.strip()) > len("WARNING:"), (
                f"WARNING line too short to contain error detail: {ln!r}"
            )
    finally:
        os.unlink(ds)
        srv.shutdown()


# ---------------------------------------------------------------------------
# AC2 — all queries failing → non-zero exit regardless of RECALL_THRESHOLD
# ---------------------------------------------------------------------------

def test_ac2_all_fail_exits_nonzero():
    """All queries return 500 → non-zero exit even with RECALL_THRESHOLD=0.0."""
    port = 21605
    srv = _start_server(port, 500, b"Server Error")
    ds = _write_dataset(_TINY_DATASET)
    try:
        r = _run_eval({"SEARCH_URL": f"http://localhost:{port}/search",
                       "K": "5", "RECALL_THRESHOLD": "0.0", "EVAL_DATASET": ds})
        assert r.returncode != 0, (
            f"Expected non-zero exit when all queries fail, got 0:\n"
            f"stdout: {r.stdout}\nstderr: {r.stderr}"
        )
    finally:
        os.unlink(ds)
        srv.shutdown()


def test_ac2_all_fail_stderr_explains_abort():
    """When all queries fail, stderr must explain why (not just a recall FAIL line)."""
    port = 21606
    srv = _start_server(port, 500, b"Server Error")
    ds = _write_dataset(_TWO_ENTRY_DATASET)
    try:
        r = _run_eval({"SEARCH_URL": f"http://localhost:{port}/search",
                       "K": "5", "RECALL_THRESHOLD": "0.0", "EVAL_DATASET": ds})
        stderr = r.stderr.lower()
        assert "error" in stderr or "warning" in stderr, (
            f"Expected ERROR or WARNING in stderr when all queries fail, got:\n{r.stderr}"
        )
    finally:
        os.unlink(ds)
        srv.shutdown()


def test_ac2_all_fail_via_connection_refused():
    """Connection refused on all queries → non-zero exit."""
    # Port 21607: intentionally no server
    ds = _write_dataset(_TINY_DATASET)
    try:
        r = _run_eval({"SEARCH_URL": "http://localhost:21607/search",
                       "K": "5", "RECALL_THRESHOLD": "0.0", "EVAL_DATASET": ds})
        assert r.returncode != 0, (
            f"Expected non-zero exit for all connection-refused queries, got 0:\n"
            f"stdout: {r.stdout}\nstderr: {r.stderr}"
        )
    finally:
        os.unlink(ds)


def test_ac2_partial_success_does_not_trigger_abort():
    """If at least one query succeeds, the all-fail abort must NOT fire.

    Uses a 200-success server; RECALL_THRESHOLD=0.0 ensures exit 0 on success.
    """
    port = 21608
    srv = _start_server(port, 200, b'{"results":[{"id":"article-thai-001","score":0.9}]}')
    ds = _write_dataset(_TINY_DATASET)
    try:
        r = _run_eval({"SEARCH_URL": f"http://localhost:{port}/search",
                       "K": "5", "RECALL_THRESHOLD": "0.0", "EVAL_DATASET": ds})
        assert r.returncode == 0, (
            f"Expected exit 0 when queries succeed (RECALL_THRESHOLD=0.0), got {r.returncode}:\n"
            f"stdout: {r.stdout}\nstderr: {r.stderr}"
        )
    finally:
        os.unlink(ds)
        srv.shutdown()
