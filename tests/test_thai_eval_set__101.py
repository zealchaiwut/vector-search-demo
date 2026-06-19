"""
Tests for issue #101: Add Thai evaluation set with recall-at-k reporting.

AC1  - Thai evaluation dataset exists under src/eval/ with ≥10 Thai queries,
       each mapped to one or more expected article IDs
AC2  - eval command (python src/eval/run_eval.py) executes without manual intervention
AC3  - prints recall@1, recall@5, and recall@10 to stdout in human-readable format
AC4  - for every query, correct Thai doc(s) appear in top-k (k=10) against correct corpus
       (tested structurally — runtime behaviour depends on live corpus)
AC5  - script exits non-zero if recall@10 < defined threshold (default 0.80)
AC6  - dataset file format is documented in src/eval/
"""

import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVAL_DIR = os.path.join(REPO_ROOT, "src", "eval")
DATASET_PATH = os.path.join(EVAL_DIR, "thai_eval_set.json")
SCRIPT_PATH = os.path.join(EVAL_DIR, "run_eval.py")


# ---------------------------------------------------------------------------
# Mock search HTTP server (handles GET /search?q=...&k=...)
# ---------------------------------------------------------------------------

class _MockSearchHandler(BaseHTTPRequestHandler):
    results_factory = None  # callable(query, k) -> list[dict]

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        query = params.get("q", [""])[0]
        k = int(params.get("k", ["10"])[0])
        results = (
            self.__class__.results_factory(query, k)
            if self.__class__.results_factory else []
        )
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
    srv = HTTPServer(("127.0.0.1", port), _MockSearchHandler)
    t = threading.Thread(target=srv.serve_forever)
    t.daemon = True
    t.start()
    return srv


def _run_eval_py(extra_env=None):
    env = {**os.environ}
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["python", SCRIPT_PATH],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


# ---------------------------------------------------------------------------
# AC1 — dataset exists, has ≥10 Thai queries, correct structure
# ---------------------------------------------------------------------------

def test_ac1_dataset_file_exists():
    """src/eval/thai_eval_set.json must exist."""
    assert os.path.isfile(DATASET_PATH), f"Missing: {DATASET_PATH}"


def test_ac1_dataset_has_at_least_10_queries():
    """Dataset must contain at minimum 10 query entries."""
    with open(DATASET_PATH, encoding="utf-8") as f:
        entries = json.load(f)
    assert isinstance(entries, list), "Dataset must be a JSON array"
    assert len(entries) >= 10, f"Expected ≥10 queries, got {len(entries)}"


def test_ac1_each_entry_has_query_and_expected():
    """Every dataset entry must have 'query' (str) and 'expected' (list of str) fields."""
    with open(DATASET_PATH, encoding="utf-8") as f:
        entries = json.load(f)
    for i, entry in enumerate(entries):
        assert "query" in entry, f"Entry {i} missing 'query' field"
        assert "expected" in entry, f"Entry {i} missing 'expected' field"
        assert isinstance(entry["query"], str), f"Entry {i} 'query' must be a string"
        assert isinstance(entry["expected"], list), f"Entry {i} 'expected' must be a list"
        assert len(entry["expected"]) >= 1, f"Entry {i} 'expected' must name at least one article ID"


def test_ac1_queries_contain_thai_characters():
    """Each query must contain at least one Thai Unicode character (U+0E00–U+0E7F)."""
    with open(DATASET_PATH, encoding="utf-8") as f:
        entries = json.load(f)
    for i, entry in enumerate(entries):
        query = entry["query"]
        has_thai = any("฀" <= ch <= "๿" for ch in query)
        assert has_thai, f"Entry {i} query '{query}' contains no Thai characters"


def test_ac1_expected_ids_reference_thai_articles():
    """Expected article IDs in the dataset must reference Thai article(s)."""
    with open(DATASET_PATH, encoding="utf-8") as f:
        entries = json.load(f)
    all_ids = {aid for entry in entries for aid in entry["expected"]}
    has_thai_article = any("thai" in aid.lower() for aid in all_ids)
    assert has_thai_article, f"No Thai article IDs found in expected sets: {all_ids}"


# ---------------------------------------------------------------------------
# AC2 — run_eval.py exists and runs without manual intervention
# ---------------------------------------------------------------------------

def test_ac2_run_eval_py_exists():
    """src/eval/run_eval.py must exist."""
    assert os.path.isfile(SCRIPT_PATH), f"Missing: {SCRIPT_PATH}"


def test_ac2_script_runs_without_crash_against_mock():
    """Script must complete (any exit code) without crashing when server is up."""
    port = 18101
    srv = _start_mock_server(port, lambda q, k: [])
    try:
        result = _run_eval_py({
            "SEARCH_URL": f"http://127.0.0.1:{port}/search",
            "RECALL_THRESHOLD": "0.0",
        })
        # Should not raise unhandled Python exception
        assert "Traceback" not in result.stderr, \
            f"Script crashed:\n{result.stderr}"
        assert len(result.stdout.strip()) > 0, "Script produced no output"
    finally:
        srv.shutdown()


# ---------------------------------------------------------------------------
# AC3 — prints recall@1, recall@5, and recall@10
# ---------------------------------------------------------------------------

def test_ac3_prints_recall_at_1():
    """stdout must contain a recall@1 line."""
    port = 18201
    srv = _start_mock_server(port, lambda q, k: [])
    try:
        result = _run_eval_py({
            "SEARCH_URL": f"http://127.0.0.1:{port}/search",
            "RECALL_THRESHOLD": "0.0",
        })
        out = result.stdout + result.stderr
        assert "recall@1" in out.lower(), f"recall@1 not found in output:\n{out}"
    finally:
        srv.shutdown()


def test_ac3_prints_recall_at_5():
    """stdout must contain a recall@5 line."""
    port = 18202
    srv = _start_mock_server(port, lambda q, k: [])
    try:
        result = _run_eval_py({
            "SEARCH_URL": f"http://127.0.0.1:{port}/search",
            "RECALL_THRESHOLD": "0.0",
        })
        out = result.stdout + result.stderr
        assert "recall@5" in out.lower(), f"recall@5 not found in output:\n{out}"
    finally:
        srv.shutdown()


def test_ac3_prints_recall_at_10():
    """stdout must contain a recall@10 line."""
    port = 18203
    srv = _start_mock_server(port, lambda q, k: [])
    try:
        result = _run_eval_py({
            "SEARCH_URL": f"http://127.0.0.1:{port}/search",
            "RECALL_THRESHOLD": "0.0",
        })
        out = result.stdout + result.stderr
        assert "recall@10" in out.lower(), f"recall@10 not found in output:\n{out}"
    finally:
        srv.shutdown()


def test_ac3_recall_output_is_human_readable():
    """Recall lines must include a fraction or percentage value."""
    port = 18204
    srv = _start_mock_server(port, lambda q, k: [])
    try:
        result = _run_eval_py({
            "SEARCH_URL": f"http://127.0.0.1:{port}/search",
            "RECALL_THRESHOLD": "0.0",
        })
        out = result.stdout
        # Expect patterns like "0.00", "10/10", or a percentage
        has_fraction = "/" in out
        has_decimal = any(c.isdigit() and "." in out for c in out)
        assert has_fraction or has_decimal, f"No numeric recall value found in:\n{out}"
    finally:
        srv.shutdown()


# ---------------------------------------------------------------------------
# AC5 — exits non-zero when recall@10 < threshold
# ---------------------------------------------------------------------------

def test_ac5_exit_nonzero_when_all_miss_and_threshold_08():
    """Exit non-zero when all queries miss and threshold is 0.80 (default)."""
    port = 18501
    srv = _start_mock_server(port, lambda q, k: [])
    try:
        result = _run_eval_py({
            "SEARCH_URL": f"http://127.0.0.1:{port}/search",
            "RECALL_THRESHOLD": "0.8",
        })
        assert result.returncode != 0, \
            f"Expected non-zero exit with 0 recall vs threshold=0.8, got {result.returncode}"
    finally:
        srv.shutdown()


def test_ac5_exit_zero_when_threshold_is_zero():
    """Exit 0 when RECALL_THRESHOLD=0.0 even with all misses."""
    port = 18502
    srv = _start_mock_server(port, lambda q, k: [])
    try:
        result = _run_eval_py({
            "SEARCH_URL": f"http://127.0.0.1:{port}/search",
            "RECALL_THRESHOLD": "0.0",
        })
        assert result.returncode == 0, \
            f"Expected exit 0 with threshold=0.0, got {result.returncode}\n{result.stderr}"
    finally:
        srv.shutdown()


def test_ac5_exit_zero_when_all_queries_hit():
    """Exit 0 when every query returns its expected article in top-10."""
    port = 18503
    # Return all possible Thai article IDs to guarantee all queries hit
    def factory(q, k):
        return [
            {"id": "article-thai-001", "score": 0.99},
            {"id": "article-thai-002", "score": 0.95},
            {"id": "article-thai-003", "score": 0.90},
        ]
    srv = _start_mock_server(port, factory)
    try:
        result = _run_eval_py({
            "SEARCH_URL": f"http://127.0.0.1:{port}/search",
            "RECALL_THRESHOLD": "1.0",
        })
        assert result.returncode == 0, \
            f"Expected exit 0 when all queries hit, got {result.returncode}\n{result.stdout}\n{result.stderr}"
    finally:
        srv.shutdown()


def test_ac5_exit_nonzero_message_printed_on_failure():
    """A FAIL message must appear in stdout/stderr when threshold is not met."""
    port = 18504
    srv = _start_mock_server(port, lambda q, k: [])
    try:
        result = _run_eval_py({
            "SEARCH_URL": f"http://127.0.0.1:{port}/search",
            "RECALL_THRESHOLD": "1.0",
        })
        out = result.stdout + result.stderr
        assert "fail" in out.lower() or "below" in out.lower(), \
            f"Expected failure message, got:\n{out}"
    finally:
        srv.shutdown()


# ---------------------------------------------------------------------------
# AC6 — dataset format is documented
# ---------------------------------------------------------------------------

def test_ac6_documentation_exists_in_eval_dir():
    """src/eval/ must contain a README.md or similar documentation file."""
    candidates = ["README.md", "README.txt", "SCHEMA.md"]
    found = any(
        os.path.isfile(os.path.join(EVAL_DIR, name))
        for name in candidates
    )
    assert found, f"No documentation file found in {EVAL_DIR}. Expected one of: {candidates}"


def test_ac6_readme_mentions_json_format():
    """README must mention the JSON schema (query and expected fields)."""
    readme_path = os.path.join(EVAL_DIR, "README.md")
    if not os.path.isfile(readme_path):
        pytest.skip("README.md not found — checked by test_ac6_documentation_exists_in_eval_dir")
    with open(readme_path, encoding="utf-8") as f:
        content = f.read()
    assert "query" in content, "README must describe the 'query' field"
    assert "expected" in content, "README must describe the 'expected' field"
