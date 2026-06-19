"""Tests for issue #9: Add recall@k evaluation script for search quality (tester)

Runs `npm run eval` via subprocess against a local mock search server.
UAT_BASE_URL / UAT_PORT are not applicable here — this feature is a CLI
script, not an HTTP endpoint.  The mock server substitutes for the live
search backend so the eval logic can be exercised without a real collection.
"""
import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ──────────────────────────────────────────────
# Mock search server helpers
# ──────────────────────────────────────────────

class _Handler(BaseHTTPRequestHandler):
    results_factory = None

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


def _start_server(port, factory):
    _Handler.results_factory = factory
    srv = HTTPServer(("localhost", port), _Handler)
    t = threading.Thread(target=srv.serve_forever)
    t.daemon = True
    t.start()
    return srv


def _run_eval(**env_overrides):
    env = {**os.environ}
    env.update(env_overrides)
    return subprocess.run(
        ["npm", "run", "eval", "--silent"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )


# ──────────────────────────────────────────────
# AC1 — script location and npm wiring
# ──────────────────────────────────────────────

def test_recall_k_evaluation_script__script_exists_in_src_eval():
    # AC: Script lives at src/eval/ and is wired to npm run eval in package.json
    eval_dir = os.path.join(REPO_ROOT, "src", "eval")
    assert os.path.isdir(eval_dir), "src/eval/ directory missing"
    entries = os.listdir(eval_dir)
    assert any(f in entries for f in ("index.js", "index.ts", "index.mjs")), \
        f"No entry-point in src/eval/: {entries}"


def test_recall_k_evaluation_script__npm_run_eval_wired():
    # AC: npm run eval wired in package.json
    pkg = os.path.join(REPO_ROOT, "package.json")
    assert os.path.isfile(pkg), "package.json not found"
    data = json.loads(open(pkg).read())
    scripts = data.get("scripts", {})
    assert "eval" in scripts, f"'eval' missing from package.json scripts: {list(scripts)}"


# ──────────────────────────────────────────────
# AC2 — min 5 hardcoded queries with expected doc_ids
# ──────────────────────────────────────────────

def test_recall_k_evaluation_script__min_five_queries_hardcoded():
    # AC: Sample query set is hardcoded (minimum 5 queries)
    for fname in ("index.js", "index.ts", "index.mjs"):
        path = os.path.join(REPO_ROOT, "src", "eval", fname)
        if os.path.isfile(path):
            src = open(path).read()
            count = src.count('"query"') + src.count("'query'")
            assert count >= 5, f"Expected ≥5 hardcoded queries, found {count}"
            return
    pytest.fail("No eval entry-point found")


# ──────────────────────────────────────────────
# AC4 — per-query output format
# ──────────────────────────────────────────────

def test_recall_k_evaluation_script__per_query_hit_miss_printed():
    # AC: Per-query output shows hit/miss label
    port = 29401
    srv = _start_server(port, lambda _: [])
    try:
        r = _run_eval(SEARCH_URL=f"http://localhost:{port}/search", RECALL_THRESHOLD="0.0")
        out = r.stdout + r.stderr
        assert "HIT" in out or "MISS" in out, f"HIT/MISS label absent:\n{out}"
    finally:
        srv.shutdown()


# ──────────────────────────────────────────────
# AC5 — overall recall@k summary line
# ──────────────────────────────────────────────

def test_recall_k_evaluation_script__recall_summary_line_printed():
    # AC: Overall recall@k figure printed at end (e.g. Recall@5: 0.80 (4/5 queries passed))
    port = 29501
    srv = _start_server(port, lambda _: [])
    try:
        r = _run_eval(SEARCH_URL=f"http://localhost:{port}/search", RECALL_THRESHOLD="0.0", K="5")
        out = r.stdout + r.stderr
        assert "Recall@5" in out, f"Recall@5 summary absent:\n{out}"
        assert "5" in out and "/" in out, "Expected N/total fraction in output"
    finally:
        srv.shutdown()


# ──────────────────────────────────────────────
# AC6 — K and threshold configurable
# ──────────────────────────────────────────────

def test_recall_k_evaluation_script__k_env_var_changes_summary():
    # AC: k configurable (env var K)
    port = 29601
    srv = _start_server(port, lambda _: [])
    try:
        r = _run_eval(SEARCH_URL=f"http://localhost:{port}/search", K="1", RECALL_THRESHOLD="0.0")
        out = r.stdout + r.stderr
        assert "Recall@1" in out, f"Expected Recall@1 with K=1:\n{out}"
    finally:
        srv.shutdown()


def test_recall_k_evaluation_script__zero_threshold_always_passes():
    # AC: pass threshold configurable — RECALL_THRESHOLD=0.0 exits 0 even with all misses
    port = 29602
    srv = _start_server(port, lambda _: [])
    try:
        r = _run_eval(SEARCH_URL=f"http://localhost:{port}/search", RECALL_THRESHOLD="0.0")
        assert r.returncode == 0, \
            f"Expected exit 0 with threshold=0.0 (all miss), got {r.returncode}\n{r.stdout}\n{r.stderr}"
    finally:
        srv.shutdown()


# ──────────────────────────────────────────────
# AC7 — exit codes
# ──────────────────────────────────────────────

def test_recall_k_evaluation_script__exit_0_when_all_hit():
    # AC: Exit 0 when recall >= threshold
    port = 29701
    # Return article-001 through article-020 so all 6 hardcoded queries are satisfied
    full_hits = [{"id": f"article-{i:03d}", "score": 1.0} for i in range(1, 21)]
    srv = _start_server(port, lambda _: full_hits)
    try:
        r = _run_eval(
            SEARCH_URL=f"http://localhost:{port}/search",
            RECALL_THRESHOLD="1.0",
            K="20",
        )
        assert r.returncode == 0, \
            f"Expected exit 0 when all queries hit, got {r.returncode}\n{r.stdout}\n{r.stderr}"
    finally:
        srv.shutdown()


def test_recall_k_evaluation_script__exit_nonzero_when_all_miss():
    # AC: Exit non-zero when recall < threshold
    port = 29702
    srv = _start_server(port, lambda _: [])
    try:
        r = _run_eval(SEARCH_URL=f"http://localhost:{port}/search", RECALL_THRESHOLD="1.0")
        assert r.returncode != 0, \
            f"Expected non-zero exit when all miss with threshold=1.0, got {r.returncode}"
    finally:
        srv.shutdown()


def test_recall_k_evaluation_script__exit_nonzero_empty_collection_no_crash():
    # AC (UAT Step 5): empty collection → non-zero exit, no crash, clear output
    port = 29703
    srv = _start_server(port, lambda _: [])
    try:
        r = _run_eval(SEARCH_URL=f"http://localhost:{port}/search", RECALL_THRESHOLD="0.8")
        out = r.stdout + r.stderr
        assert r.returncode != 0, "Exit must be non-zero with empty collection"
        assert len(out.strip()) > 0, "Output must not be empty on failure"
        # No unhandled exceptions
        assert "Error:" not in out or "FAIL" in out, \
            f"Unexpected unhandled error in output:\n{out}"
    finally:
        srv.shutdown()


# ──────────────────────────────────────────────
# AC8 — CI quality gate (UAT Steps 3–4)
# ──────────────────────────────────────────────

def test_recall_k_evaluation_script__high_threshold_triggers_failure():
    # UAT Step 3: threshold above actual recall → non-zero exit + clear failure message
    port = 29801
    srv = _start_server(port, lambda _: [])
    try:
        r = _run_eval(SEARCH_URL=f"http://localhost:{port}/search", RECALL_THRESHOLD="1.0")
        assert r.returncode != 0
        out = r.stdout + r.stderr
        assert "FAIL" in out or "fail" in out.lower(), \
            f"Expected FAIL message when threshold not met:\n{out}"
    finally:
        srv.shutdown()


def test_recall_k_evaluation_script__k1_uses_single_top_result():
    # UAT Step 4: K=1 → recall computed on single top result per query
    port = 29802
    # Return only article-001 (first expected article); with K=1 this should be a HIT for query 1
    srv = _start_server(port, lambda _: [{"id": "article-001", "score": 1.0}])
    try:
        r = _run_eval(
            SEARCH_URL=f"http://localhost:{port}/search",
            K="1",
            RECALL_THRESHOLD="0.0",
        )
        out = r.stdout + r.stderr
        assert "Recall@1" in out, f"Expected Recall@1 summary with K=1:\n{out}"
    finally:
        srv.shutdown()
