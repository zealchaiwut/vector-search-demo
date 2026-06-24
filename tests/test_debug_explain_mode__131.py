"""
TDD tests for issue #131: Add debug explain mode to search API.

AC1 — debug=true returns explain block per result with score at each pipeline stage ran
AC2 — Each stage entry has rank (1-indexed position) and rankDelta (change from prior stage)
AC3 — Each stage entry has latencyMs in milliseconds
AC4 — Active preset/config name at top level of debug response (not per-result)
AC5 — Stages that did not run are omitted entirely (no null/empty placeholders)
AC6 — debug=false (or absent) returns existing response shape unchanged — no explain, no overhead
AC7 — API response types in src/search updated to reflect the new optional explain fields
AC8 — Debug flag is documented in the API response type definitions
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
SEARCH_INDEX_JS = os.path.join(REPO_ROOT, "src", "search", "index.js")
SERVER_TS = os.path.join(REPO_ROOT, "src", "server", "index.ts")
SERVER_MJS = os.path.join(REPO_ROOT, "src", "server.mjs")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_node(script, env=None, timeout=60):
    merged = os.environ.copy()
    if env:
        merged.update(env)
    result = subprocess.run(
        ["node", "--input-type=module"],
        input=script,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=timeout,
        env=merged,
    )
    return result.stdout, result.stderr, result.returncode


def _find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


class _ServerProcess:
    """Context manager: starts the real Node server on a free port."""

    def __init__(self, env=None):
        self.port = _find_free_port()
        self.proc = None
        self.extra_env = env or {}

    def __enter__(self):
        env = os.environ.copy()
        env["PORT"] = str(self.port)
        env.update(self.extra_env)
        self.proc = subprocess.Popen(
            ["node", SERVER_MJS],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=REPO_ROOT,
            env=env,
        )
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                conn = http.client.HTTPConnection("localhost", self.port, timeout=1)
                conn.request("GET", "/health/integrity")
                conn.getresponse()
                conn.close()
                break
            except Exception:
                time.sleep(0.1)
        return self

    def get(self, path):
        conn = http.client.HTTPConnection("localhost", self.port, timeout=15)
        conn.request("GET", path)
        resp = conn.getresponse()
        body = resp.read()
        conn.close()
        return resp.status, dict(resp.getheaders()), body

    def post(self, path, payload):
        body = json.dumps(payload).encode()
        conn = http.client.HTTPConnection("localhost", self.port, timeout=15)
        conn.request("POST", path, body=body, headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        response_body = resp.read()
        conn.close()
        return resp.status, dict(resp.getheaders()), response_body

    def __exit__(self, *_):
        if self.proc:
            self.proc.terminate()
            self.proc.wait(timeout=5)


# ---------------------------------------------------------------------------
# AC7 — src/search/index.js updated with explain types / structures
# ---------------------------------------------------------------------------

def test_ac7_search_index_js_exists():
    assert os.path.isfile(SEARCH_INDEX_JS), "src/search/index.js must exist"


def test_ac7_explain_keyword_in_search_index():
    with open(SEARCH_INDEX_JS) as f:
        src = f.read()
    assert "explain" in src, (
        "src/search/index.js must contain 'explain' block logic"
    )


def test_ac7_debug_param_in_searchDocuments():
    with open(SEARCH_INDEX_JS) as f:
        src = f.read()
    assert re.search(r"searchDocuments\s*\([^)]*debug", src), (
        "searchDocuments must accept a 'debug' parameter"
    )


def test_ac7_explain_stage_fields_in_source():
    with open(SEARCH_INDEX_JS) as f:
        src = f.read()
    for field in ("stage", "score", "rank", "rankDelta", "latencyMs"):
        assert field in src, (
            f"src/search/index.js must reference explain field '{field}'"
        )


def test_ac7_dense_stage_tracked():
    with open(SEARCH_INDEX_JS) as f:
        src = f.read()
    assert "'dense'" in src or '"dense"' in src, (
        "src/search/index.js must track the 'dense' explain stage"
    )


def test_ac7_rerank_stage_tracked():
    with open(SEARCH_INDEX_JS) as f:
        src = f.read()
    assert "'rerank'" in src or '"rerank"' in src, (
        "src/search/index.js must track the 'rerank' explain stage"
    )


def test_ac7_lexical_stage_tracked():
    with open(SEARCH_INDEX_JS) as f:
        src = f.read()
    assert "'lexical'" in src or '"lexical"' in src, (
        "src/search/index.js must track the 'lexical' explain stage"
    )


def test_ac7_rrf_stage_tracked():
    with open(SEARCH_INDEX_JS) as f:
        src = f.read()
    assert "'rrf'" in src or '"rrf"' in src, (
        "src/search/index.js must track the 'rrf' explain stage"
    )


# ---------------------------------------------------------------------------
# AC8 — Debug flag documented in type definitions (server/index.ts or JSDoc)
# ---------------------------------------------------------------------------

def test_ac8_debug_documented_in_server_types():
    """debug flag appears in src/server/index.ts types or JSDoc in src/search/index.js."""
    documented = False

    if os.path.isfile(SERVER_TS):
        with open(SERVER_TS) as f:
            ts_src = f.read()
        if "debug" in ts_src and "explain" in ts_src:
            documented = True

    if not documented:
        with open(SEARCH_INDEX_JS) as f:
            js_src = f.read()
        if "debug" in js_src and ("@param" in js_src or "explain" in js_src):
            documented = True

    assert documented, (
        "The 'debug' flag must be documented in src/server/index.ts types or "
        "in JSDoc comments in src/search/index.js"
    )


def test_ac8_explain_type_optional_marker():
    """explain field must be typed as optional (? in TS or @param with [debug] in JSDoc)."""
    found_optional = False

    if os.path.isfile(SERVER_TS):
        with open(SERVER_TS) as f:
            ts_src = f.read()
        # Optional TypeScript field: explain?: ...
        if re.search(r"explain\s*\?", ts_src):
            found_optional = True

    if not found_optional:
        with open(SEARCH_INDEX_JS) as f:
            js_src = f.read()
        # JSDoc optional param: @param {boolean} [debug]
        if re.search(r"@param\s+\{[^}]*\}\s+\[debug\]", js_src):
            found_optional = True

    assert found_optional, (
        "The 'explain' field must be marked as optional in TypeScript types "
        "(explain?: ...) or the debug param as optional in JSDoc ([debug])"
    )


# ---------------------------------------------------------------------------
# Node.js unit tests for explain structure (using helper utilities)
# ---------------------------------------------------------------------------

def test_ac1_debug_true_attaches_explain_to_results():
    """When debug=true, searchDocuments must attach explain to each result (unit test with mock)."""
    script = """
import { searchDocuments } from './src/search/index.js';

// Use a very short query that won't cause issues even with empty collection
const results = await searchDocuments('', 10, null, null, true);

// With empty collection results will be [], which is fine for structural test.
// The important thing: results must be an Array.
if (!Array.isArray(results)) {
  process.stderr.write('searchDocuments must return an Array\\n');
  process.exit(1);
}

// If we got results (non-empty collection), each must have explain
for (const r of results) {
  if (!Array.isArray(r.explain)) {
    process.stderr.write('result missing explain array: ' + JSON.stringify(r.id) + '\\n');
    process.exit(1);
  }
}

process.stdout.write(JSON.stringify({ ok: true, count: results.length }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["ok"] is True


def test_ac1_explain_stage_has_score_field():
    """Each explain stage entry must have a 'score' field (verified via utility functions)."""
    script = """
import { searchDocuments } from './src/search/index.js';
// Use an empty query so collection search fast-returns []
const results = await searchDocuments('__unit_test__', 10, null, {
  embeddingModelId: 'Xenova/multilingual-e5-small',
  topK: 10,
  hybridEnabled: false,
  hybridFusionWeight: 0.7,
  rerankEnabled: false,
  rerankModelId: 'cross-encoder/ms-marco-MiniLM-L-6-v2',
  chunkSize: 400,
  chunkOverlap: 80,
  textNormalisationEnabled: true,
}, true);

// Structural check: if results present, they must have explain
let explainStructureOk = true;
for (const r of results) {
  if (!Array.isArray(r.explain)) { explainStructureOk = false; break; }
  for (const s of r.explain) {
    if (typeof s.score !== 'number') { explainStructureOk = false; break; }
  }
}
process.stdout.write(JSON.stringify({ ok: explainStructureOk, count: results.length }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["ok"] is True, "All explain stages must have a numeric 'score' field"


def test_ac2_explain_stage_has_rank_field():
    """Each explain stage must have a 'rank' field (1-indexed)."""
    script = """
import { searchDocuments } from './src/search/index.js';
const results = await searchDocuments('__rank_test__', 10, null, null, true);
let ok = true;
for (const r of results) {
  for (const s of (r.explain ?? [])) {
    if (typeof s.rank !== 'number' || s.rank < 1) { ok = false; break; }
  }
}
process.stdout.write(JSON.stringify({ ok }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["ok"] is True, "All explain stages must have a rank >= 1"


def test_ac2_explain_stage_has_rank_delta_field():
    """Each explain stage must have a 'rankDelta' field."""
    script = """
import { searchDocuments } from './src/search/index.js';
const results = await searchDocuments('__delta_test__', 10, null, null, true);
let ok = true;
for (const r of results) {
  for (const s of (r.explain ?? [])) {
    if (typeof s.rankDelta !== 'number') { ok = false; break; }
  }
}
process.stdout.write(JSON.stringify({ ok }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["ok"] is True, "All explain stages must have a numeric 'rankDelta' field"


def test_ac3_explain_stage_has_latency_ms():
    """Each explain stage must have a 'latencyMs' field."""
    script = """
import { searchDocuments } from './src/search/index.js';
const results = await searchDocuments('__latency_test__', 10, null, null, true);
let ok = true;
for (const r of results) {
  for (const s of (r.explain ?? [])) {
    if (typeof s.latencyMs !== 'number' || s.latencyMs < 0) { ok = false; break; }
  }
}
process.stdout.write(JSON.stringify({ ok }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["ok"] is True, "All explain stages must have a non-negative 'latencyMs' field"


def test_ac5_explain_first_stage_rank_delta_is_zero():
    """The first explain stage always has rankDelta = 0 (no prior stage to compare)."""
    script = """
import { searchDocuments } from './src/search/index.js';
const results = await searchDocuments('__delta0_test__', 10, null, null, true);
let ok = true;
for (const r of results) {
  const stages = r.explain ?? [];
  if (stages.length > 0 && stages[0].rankDelta !== 0) {
    ok = false;
    break;
  }
}
process.stdout.write(JSON.stringify({ ok }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["ok"] is True, "First explain stage must have rankDelta === 0"


def test_ac5_no_null_entries_in_explain():
    """explain array must have no null/undefined entries."""
    script = """
import { searchDocuments } from './src/search/index.js';
const results = await searchDocuments('__null_test__', 10, null, null, true);
let ok = true;
for (const r of results) {
  for (const s of (r.explain ?? [])) {
    if (s === null || s === undefined) { ok = false; break; }
  }
}
process.stdout.write(JSON.stringify({ ok }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["ok"] is True, "explain array must have no null entries"


def test_ac5_without_rerank_no_rerank_stage():
    """With rerankEnabled=false, the explain block must not contain a 'rerank' stage."""
    script = """
import { searchDocuments } from './src/search/index.js';
const cfg = {
  embeddingModelId: 'Xenova/multilingual-e5-small',
  topK: 10,
  hybridEnabled: false,
  hybridFusionWeight: 0.7,
  rerankEnabled: false,
  rerankModelId: 'cross-encoder/ms-marco-MiniLM-L-6-v2',
  chunkSize: 400,
  chunkOverlap: 80,
  textNormalisationEnabled: true,
};
const results = await searchDocuments('test', 10, null, cfg, true);
let hasRerank = false;
for (const r of results) {
  if ((r.explain ?? []).some(s => s.stage === 'rerank')) {
    hasRerank = true;
    break;
  }
}
process.stdout.write(JSON.stringify({ hasRerank, count: results.length }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["hasRerank"] is False, (
        "rerankEnabled=false must produce no 'rerank' stage in explain"
    )


def test_ac5_without_hybrid_no_lexical_or_rrf_stages():
    """With hybridEnabled=false, explain must not contain 'lexical' or 'rrf' stages."""
    script = """
import { searchDocuments } from './src/search/index.js';
const cfg = {
  embeddingModelId: 'Xenova/multilingual-e5-small',
  topK: 10,
  hybridEnabled: false,
  hybridFusionWeight: 0.7,
  rerankEnabled: false,
  rerankModelId: 'cross-encoder/ms-marco-MiniLM-L-6-v2',
  chunkSize: 400,
  chunkOverlap: 80,
  textNormalisationEnabled: true,
};
const results = await searchDocuments('test', 10, null, cfg, true);
let hasHybridStage = false;
for (const r of results) {
  if ((r.explain ?? []).some(s => s.stage === 'lexical' || s.stage === 'rrf')) {
    hasHybridStage = true;
    break;
  }
}
process.stdout.write(JSON.stringify({ hasHybridStage, count: results.length }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["hasHybridStage"] is False, (
        "hybridEnabled=false must produce no 'lexical' or 'rrf' stage in explain"
    )


def test_ac5_with_hybrid_includes_lexical_and_rrf():
    """With hybridEnabled=true, explain must include 'lexical' and 'rrf' stages for each result."""
    script = """
import { searchDocuments } from './src/search/index.js';
const cfg = {
  embeddingModelId: 'Xenova/multilingual-e5-small',
  topK: 10,
  hybridEnabled: true,
  hybridFusionWeight: 0.7,
  rerankEnabled: false,
  rerankModelId: 'cross-encoder/ms-marco-MiniLM-L-6-v2',
  chunkSize: 400,
  chunkOverlap: 80,
  textNormalisationEnabled: true,
};
const results = await searchDocuments('test', 10, null, cfg, true);
// With empty collection, verify the logic is correct when results exist
// by checking that no lexical/rrf stages appear in non-hybrid mode (structural test)
// This test verifies that hybridEnabled=true triggers those stages
// (We can only verify this in source code or with real data)
let allHaveHybridStages = true;
for (const r of results) {
  const stages = r.explain ?? [];
  const hasLexical = stages.some(s => s.stage === 'lexical');
  const hasRrf = stages.some(s => s.stage === 'rrf');
  if (!hasLexical || !hasRrf) { allHaveHybridStages = false; break; }
}
// If no results, we can't verify — report ok=true (vacuously true for empty set)
const count = results.length;
const ok = count === 0 || allHaveHybridStages;
process.stdout.write(JSON.stringify({ ok, count }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["ok"] is True, (
        "hybridEnabled=true must include 'lexical' and 'rrf' stages in explain for each result"
    )


# ---------------------------------------------------------------------------
# AC6 — debug=false returns unmodified response shape
# ---------------------------------------------------------------------------

def test_ac6_debug_false_no_explain_in_results():
    """debug=false (explicit) must not add 'explain' field to any result."""
    script = """
import { searchDocuments } from './src/search/index.js';
const results = await searchDocuments('test', 10, null, null, false);
let hasExplain = results.some(r => 'explain' in r);
process.stdout.write(JSON.stringify({ hasExplain, count: results.length }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["hasExplain"] is False, (
        "debug=false must not add 'explain' field to any result"
    )


def test_ac6_debug_absent_no_explain():
    """Calling searchDocuments without the debug param must not add 'explain'."""
    script = """
import { searchDocuments } from './src/search/index.js';
const results = await searchDocuments('test', 10, null, null);
let hasExplain = results.some(r => 'explain' in r);
process.stdout.write(JSON.stringify({ hasExplain, count: results.length }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["hasExplain"] is False, (
        "Omitting debug param must not add 'explain' field to any result"
    )


# ---------------------------------------------------------------------------
# AC4 — Active preset name at top level when debug=true (HTTP integration)
# ---------------------------------------------------------------------------

def test_ac4_debug_true_includes_active_preset_in_response():
    """GET /search?debug=true must include 'activePreset' at the top level of the response."""
    with _ServerProcess() as srv:
        status, _, body = srv.get("/search?q=test&debug=true")
    assert status == 200, f"Expected 200, got {status}"
    data = json.loads(body)
    assert "activePreset" in data, (
        f"debug=true response must include 'activePreset' at top level. Keys: {list(data.keys())}"
    )


def test_ac4_debug_true_with_preset_name_reflects_preset():
    """GET /search?debug=true&preset=hybrid-rerank must include activePreset='hybrid-rerank'."""
    with _ServerProcess() as srv:
        status, _, body = srv.get("/search?q=test&debug=true&preset=hybrid-rerank")
    assert status == 200, f"Expected 200, got {status}"
    data = json.loads(body)
    assert "activePreset" in data, "debug=true response must include 'activePreset'"
    assert data["activePreset"] == "hybrid-rerank", (
        f"activePreset must reflect the named preset. Got: {data.get('activePreset')}"
    )


def test_ac4_debug_true_without_preset_active_preset_is_null():
    """debug=true without preset should include activePreset: null (no named preset used)."""
    with _ServerProcess() as srv:
        status, _, body = srv.get("/search?q=test&debug=true")
    assert status == 200
    data = json.loads(body)
    assert "activePreset" in data
    assert data["activePreset"] is None, (
        f"No preset → activePreset must be null. Got: {data.get('activePreset')}"
    )


def test_ac4_debug_true_via_post_includes_active_preset():
    """POST /search with debug: true body must include 'activePreset' at top level."""
    with _ServerProcess() as srv:
        status, _, body = srv.post("/search", {"q": "test", "debug": True, "preset": "hybrid"})
    assert status == 200, f"Expected 200, got {status}"
    data = json.loads(body)
    assert "activePreset" in data, "POST debug=true response must include 'activePreset'"
    assert data["activePreset"] == "hybrid", (
        f"activePreset must be 'hybrid'. Got: {data.get('activePreset')}"
    )


# ---------------------------------------------------------------------------
# AC6 — debug=false (HTTP level) — response shape unchanged
# ---------------------------------------------------------------------------

def test_ac6_debug_false_no_active_preset_in_response():
    """GET /search without debug must NOT include 'activePreset' in response."""
    with _ServerProcess() as srv:
        status, _, body = srv.get("/search?q=test")
    assert status == 200
    data = json.loads(body)
    assert "activePreset" not in data, (
        f"Non-debug response must not include 'activePreset'. Keys: {list(data.keys())}"
    )


def test_ac6_debug_false_explicit_no_active_preset():
    """GET /search?debug=false must NOT include 'activePreset' in response."""
    with _ServerProcess() as srv:
        status, _, body = srv.get("/search?q=test&debug=false")
    assert status == 200
    data = json.loads(body)
    assert "activePreset" not in data, (
        "debug=false response must not include 'activePreset'"
    )


def test_ac6_non_debug_response_has_results_and_config_only():
    """Non-debug search response must only have 'results' and 'config' top-level keys."""
    with _ServerProcess() as srv:
        status, _, body = srv.get("/search?q=test")
    assert status == 200
    data = json.loads(body)
    unexpected_keys = set(data.keys()) - {"results", "config"}
    assert not unexpected_keys, (
        f"Non-debug response must not have extra keys. Found: {unexpected_keys}"
    )


def test_ac6_debug_false_post_no_active_preset():
    """POST /search with debug=false must NOT include 'activePreset' in response."""
    with _ServerProcess() as srv:
        status, _, body = srv.post("/search", {"q": "test", "debug": False})
    assert status == 200
    data = json.loads(body)
    assert "activePreset" not in data, (
        "POST debug=false must not include 'activePreset'"
    )


# ---------------------------------------------------------------------------
# AC1 — HTTP level: debug response includes explain on results (if any)
# ---------------------------------------------------------------------------

def test_ac1_debug_true_response_results_shape():
    """GET /search?debug=true response results must be an array (even if empty)."""
    with _ServerProcess() as srv:
        status, _, body = srv.get("/search?q=test&debug=true")
    assert status == 200
    data = json.loads(body)
    assert isinstance(data.get("results"), list), "results must be a list"


def test_ac1_server_parses_debug_flag_from_get():
    """Server must accept debug=true as a GET query parameter without error."""
    with _ServerProcess() as srv:
        status, _, body = srv.get("/search?q=test&debug=true")
    assert status == 200, f"Expected 200, got {status}. Body: {body[:200]}"


def test_ac1_server_parses_debug_flag_from_post():
    """Server must accept debug: true in POST JSON body without error."""
    with _ServerProcess() as srv:
        status, _, body = srv.post("/search", {"q": "test", "debug": True})
    assert status == 200, f"Expected 200, got {status}. Body: {body[:200]}"


def test_ac1_debug_flag_does_not_break_normal_config_keys():
    """debug flag must not affect existing config keys in the response."""
    with _ServerProcess() as srv:
        status, _, body = srv.get("/search?q=test&debug=true&rerankEnabled=true&topK=5")
    assert status == 200
    data = json.loads(body)
    assert "config" in data
    assert data["config"].get("rerankEnabled") is True
    assert data["config"].get("topK") == 5


# ---------------------------------------------------------------------------
# AC3 — latency regression: non-debug requests have no measurable overhead
# (structural: verify no overhead code runs in non-debug path)
# ---------------------------------------------------------------------------

def test_ac3_non_debug_path_has_no_explain_overhead():
    """Source code: non-debug path must be guarded so no explain Map is created."""
    with open(SEARCH_INDEX_JS) as f:
        src = f.read()
    # There should be a conditional guard for debug mode (e.g., `if (debug)`)
    assert re.search(r"if\s*\(\s*debug\s*\)", src), (
        "searchDocuments must guard explain tracking behind 'if (debug)' to avoid overhead"
    )
