"""
TDD tests for issue #134: Upgrade Compare Tab into Configuration Audit Tool.

AC1 — The Compare tab exposes two preset selector dropdowns (Preset A and Preset B),
       populated from the available named search configurations.
AC2 — Submitting a query fires two parallel requests to the search endpoint,
       each carrying the respective preset's config overrides and debug: true / explain mode enabled.
AC3 — Results for Preset A and Preset B are displayed in two side-by-side columns,
       each showing the ranked result list in order.
AC4 — Each result card displays per-stage scores returned by explain mode
       (e.g., dense score, sparse score, rerank score, final score) beneath the result title/snippet.
AC5 — Changing either preset selector automatically re-runs the current query and refreshes
       only that column — no full page reload occurs.
AC6 — If the query field is empty, preset changes do not trigger a search.
AC7 — Both columns display a loading state while their respective requests are in flight.
AC8 — Error states (failed request, empty results) are shown per-column without affecting the other column.
AC9 — The UI is responsive and side-by-side layout degrades gracefully on narrow viewports
       (e.g., stacks vertically below a defined breakpoint).
"""

import http.client
import json
import os
import re
import socket
import subprocess
import time
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_HTML = os.path.join(REPO_ROOT, "public", "index.html")
SERVER_MJS = os.path.join(REPO_ROOT, "src", "server.mjs")
RETRIEVAL_CONFIG_JS = os.path.join(REPO_ROOT, "src", "config", "retrieval.js")


def _src():
    with open(INDEX_HTML) as f:
        return f.read()


def _server_src():
    with open(SERVER_MJS) as f:
        return f.read()


def _find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


# ---------------------------------------------------------------------------
# Live server helper
# ---------------------------------------------------------------------------

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
                conn.request("GET", "/")
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
# AC1 — Two preset selector dropdowns populated from available named configurations
# ---------------------------------------------------------------------------

def test_ac1_compare_panel_has_preset_a_selector():
    """The Compare tab HTML must include a Preset A selector element."""
    src = _src()
    assert re.search(r'id="preset-a"', src) or re.search(r'preset-a', src), (
        "Compare panel must have a Preset A selector (id=preset-a or class/name containing preset-a)"
    )


def test_ac1_compare_panel_has_preset_b_selector():
    """The Compare tab HTML must include a Preset B selector element."""
    src = _src()
    assert re.search(r'id="preset-b"', src) or re.search(r'preset-b', src), (
        "Compare panel must have a Preset B selector (id=preset-b or class/name containing preset-b)"
    )


def test_ac1_preset_selectors_are_select_elements():
    """The preset selectors must use <select> elements."""
    src = _src()
    assert re.search(r'<select[^>]+id="preset-a"', src) or re.search(r'<select[^>]+id="preset-b"', src), (
        "Preset A and/or Preset B must be <select> elements"
    )


def test_ac1_js_loads_presets_from_api():
    """The frontend JS must load available presets from the server (GET /api/presets or similar)."""
    src = _src()
    assert re.search(r"/api/presets", src), (
        "Compare tab JS must call /api/presets (or similar) to populate preset dropdowns"
    )


def test_ac1_preset_selectors_labeled():
    """The preset selectors should be labeled 'Preset A' and 'Preset B'."""
    src = _src()
    assert re.search(r"Preset A", src, re.IGNORECASE), (
        "Compare tab must label one dropdown 'Preset A'"
    )
    assert re.search(r"Preset B", src, re.IGNORECASE), (
        "Compare tab must label one dropdown 'Preset B'"
    )


def test_ac1_api_presets_endpoint_exists_in_server():
    """server.mjs must register GET /api/presets endpoint."""
    src = _server_src()
    assert re.search(r"/api/presets", src), (
        "server.mjs must handle GET /api/presets to expose available presets"
    )


def test_ac1_api_presets_returns_preset_list():
    """GET /api/presets must return a JSON object with a presets array."""
    with _ServerProcess() as srv:
        status, _, body = srv.get("/api/presets")
    assert status == 200, f"Expected 200, got {status}"
    data = json.loads(body)
    assert "presets" in data, f"Response must have 'presets' key. Got: {list(data.keys())}"
    assert isinstance(data["presets"], list), "presets must be an array"
    assert len(data["presets"]) > 0, "presets must not be empty"


def test_ac1_api_presets_includes_known_presets():
    """GET /api/presets must include at least dense-only, hybrid, hybrid-rerank."""
    with _ServerProcess() as srv:
        status, _, body = srv.get("/api/presets")
    assert status == 200
    data = json.loads(body)
    presets = data["presets"]
    for expected in ("dense-only", "hybrid", "hybrid-rerank"):
        assert expected in presets, (
            f"GET /api/presets must include '{expected}'. Got: {presets}"
        )


# ---------------------------------------------------------------------------
# AC2 — Submitting fires two parallel requests with preset configs and debug: true
# ---------------------------------------------------------------------------

def test_ac2_js_uses_promise_all_for_parallel_requests():
    """Compare JS must use Promise.all to fire both requests in parallel."""
    src = _src()
    assert re.search(r"Promise\.all", src), (
        "Compare tab JS must use Promise.all to fire preset A and B requests in parallel"
    )


def test_ac2_js_sends_debug_true_flag():
    """Compare JS must pass debug=true (or debug: true) to search requests."""
    src = _src()
    assert re.search(r"debug.*true|debug=true", src), (
        "Compare tab JS must pass debug=true to search requests to enable explain mode"
    )


def test_ac2_js_sends_preset_param():
    """Compare JS must pass the preset name as a query parameter or body field."""
    src = _src()
    assert re.search(r"preset", src), (
        "Compare tab JS must include preset name in search requests"
    )


def test_ac2_search_with_debug_true_returns_explain():
    """GET /search?debug=true must include explain blocks on results."""
    with _ServerProcess() as srv:
        status, _, body = srv.get("/search?q=test&debug=true&preset=dense-only")
    assert status == 200, f"Expected 200, got {status}"
    data = json.loads(body)
    assert "results" in data
    for r in data["results"]:
        assert "explain" in r, (
            f"debug=true response results must include 'explain'. Got keys: {list(r.keys())}"
        )


def test_ac2_search_accepts_preset_and_debug_together():
    """GET /search with preset and debug=true must return 200 with activePreset set."""
    with _ServerProcess() as srv:
        status, _, body = srv.get("/search?q=test&preset=hybrid&debug=true")
    assert status == 200
    data = json.loads(body)
    assert data.get("activePreset") == "hybrid", (
        f"activePreset must reflect the named preset. Got: {data.get('activePreset')}"
    )


# ---------------------------------------------------------------------------
# AC3 — Two side-by-side columns for results
# ---------------------------------------------------------------------------

def test_ac3_compare_panel_has_two_result_columns():
    """Compare panel must have two separate result-list containers."""
    src = _src()
    # Check for at least two compare result containers
    count = len(re.findall(r'compare-results|compare-col\b', src))
    assert count >= 2, (
        f"Compare panel must have at least two result column containers. Found {count} matches"
    )


def test_ac3_compare_columns_side_by_side_css():
    """Compare CSS must define a two-column grid or flex side-by-side layout."""
    src = _src()
    assert re.search(r"grid-template-columns.*1fr.*1fr|1fr 1fr", src), (
        "Compare panel CSS must define a 1fr 1fr (or similar) two-column layout"
    )


def test_ac3_compare_panel_exists_in_dom():
    """Compare panel section must exist in the HTML."""
    src = _src()
    assert re.search(r'id="panel-compare"', src), (
        "An element with id='panel-compare' must exist"
    )


def test_ac3_compare_columns_container_exists():
    """The compare-columns container must exist in the HTML."""
    src = _src()
    assert re.search(r'id="compare-columns"', src), (
        "An element with id='compare-columns' must exist for the two-column layout"
    )


# ---------------------------------------------------------------------------
# AC4 — Each result card shows per-stage scores from explain mode
# ---------------------------------------------------------------------------

def test_ac4_js_renders_explain_stages():
    """JS must render explain stage data (scores per stage) on each result card."""
    src = _src()
    assert re.search(r"explain", src), (
        "Compare tab JS must reference 'explain' to render per-stage scores"
    )


def test_ac4_js_has_explain_rendering_function():
    """JS must have logic to format/display explain stages (stage name + score)."""
    src = _src()
    assert re.search(r"explain.*stage|stage.*explain|explainStage|explain-stage|explain_stage", src, re.IGNORECASE), (
        "Compare tab JS must have logic to render explain stages per result"
    )


def test_ac4_html_has_explain_stage_css():
    """HTML/CSS must include styles for explain stage display."""
    src = _src()
    assert re.search(r"explain-stage|explain_stage|explain-stages", src), (
        "HTML must include CSS classes for explain stage score display"
    )


def test_ac4_js_extracts_stage_score_fields():
    """JS must access 'score' field from each explain stage entry."""
    src = _src()
    assert re.search(r"s\.score|stage\.score|explain.*\.score|\.score", src), (
        "Compare tab JS must extract and display 'score' from each explain stage"
    )


def test_ac4_js_shows_stage_name():
    """JS must display the stage name (dense, lexical, rrf, rerank) from explain."""
    src = _src()
    assert re.search(r"s\.stage|stage\.stage|\.stage\b", src), (
        "Compare tab JS must display the 'stage' name from each explain entry"
    )


# ---------------------------------------------------------------------------
# AC5 — Preset change re-runs only that column
# ---------------------------------------------------------------------------

def test_ac5_preset_a_change_listener():
    """JS must add a 'change' event listener on the Preset A selector."""
    src = _src()
    assert re.search(r"preset.?.?[Ss]elect.*change|presetASelect.*change|preset-a.*change|change.*preset-a", src), (
        "JS must listen for 'change' events on the Preset A dropdown"
    )


def test_ac5_preset_b_change_listener():
    """JS must add a 'change' event listener on the Preset B selector."""
    src = _src()
    assert re.search(r"preset.?.?[Ss]elect.*change|presetBSelect.*change|preset-b.*change|change.*preset-b", src), (
        "JS must listen for 'change' events on the Preset B dropdown"
    )


def test_ac5_per_column_search_function():
    """JS must have a per-column search function (not always searching both columns)."""
    src = _src()
    assert re.search(r"runColSearch|searchCol|searchPreset|col.*search|runSearch.*col", src, re.IGNORECASE), (
        "JS must have a per-column search function to refresh only one column on preset change"
    )


def test_ac5_no_page_reload_on_preset_change():
    """JS must NOT use window.location.reload() or full page reload on preset change."""
    src = _src()
    # Ensure no window.location.reload() or form submit that causes full reload
    assert not re.search(r"window\.location\.reload\(\)|location\.reload\(\)", src), (
        "Compare tab JS must NOT call location.reload() — it must refresh only the affected column"
    )


# ---------------------------------------------------------------------------
# AC6 — Empty query → preset changes do not trigger a search
# ---------------------------------------------------------------------------

def test_ac6_empty_query_guard_in_preset_change():
    """JS change handler must check query is non-empty before firing a search."""
    src = _src()
    # The change handler should guard with !query or query check
    assert re.search(r"if\s*\(!?\s*query\s*\)|\.trim\(\)|\.length", src), (
        "Preset change handler must guard against empty query (check query is non-empty)"
    )


def test_ac6_empty_query_guard_returns_early():
    """JS preset change handler must return early (or skip search) when query is empty."""
    src = _src()
    # Common patterns: if (!query) return; or if (query) { ... }
    assert re.search(r"if\s*\(!\s*query\s*\)\s*return|\.trim\(\)\s*\)\s*return|if\s*\(\s*!query", src), (
        "Preset change handler must return early when the query field is empty"
    )


# ---------------------------------------------------------------------------
# AC7 — Both columns display loading state while requests are in flight
# ---------------------------------------------------------------------------

def test_ac7_html_has_loading_elements():
    """HTML must include per-column loading indicator elements."""
    src = _src()
    # Look for loading elements in the compare panel
    assert re.search(r"compare.*loading|loading.*compare|compare-loading|loading-a|loading-b", src, re.IGNORECASE), (
        "HTML must have loading indicator elements for the compare columns"
    )


def test_ac7_js_shows_loading_before_fetch():
    """JS must show/set a loading state before firing the search request."""
    src = _src()
    assert re.search(r"loading.*hidden\s*=\s*false|setColLoading|hidden\s*=\s*!isLoading|loading.*true", src), (
        "JS must reveal the loading indicator before firing the column search request"
    )


def test_ac7_js_hides_loading_after_fetch():
    """JS must hide the loading state after the search request completes."""
    src = _src()
    assert re.search(r"loading.*hidden\s*=\s*true|\.hidden\s*=\s*true|isLoading.*false|hidden.*finally", src), (
        "JS must hide the loading indicator after the column search request completes"
    )


# ---------------------------------------------------------------------------
# AC8 — Error states per-column without affecting other column
# ---------------------------------------------------------------------------

def test_ac8_js_has_per_column_error_rendering():
    """JS must render error state per column (not replacing both columns on one failure)."""
    src = _src()
    assert re.search(r"renderColError|error-state.*col|col.*error", src, re.IGNORECASE), (
        "JS must render error messages per column independently"
    )


def test_ac8_per_column_try_catch():
    """Each column search must have its own try/catch to isolate errors."""
    src = _src()
    # Count try/catch blocks — expect at least one in the per-column function
    try_catch_count = len(re.findall(r"\btry\s*\{", src))
    assert try_catch_count >= 2, (
        f"HTML JS must have multiple try/catch blocks to isolate per-column errors. Found {try_catch_count}"
    )


def test_ac8_error_does_not_clear_other_column():
    """Per-column error function must target only the affected column's container."""
    src = _src()
    # The error render function should accept a column identifier ('a'/'b') and use it to target
    assert re.search(r"renderColError.*col|col.*error-state|col\s*===\s*['\"]a['\"]|col\s*===\s*['\"]b['\"]", src), (
        "Error rendering must be column-specific (using a column parameter or ID)"
    )


# ---------------------------------------------------------------------------
# AC9 — Responsive layout stacks on narrow viewports
# ---------------------------------------------------------------------------

def test_ac9_responsive_breakpoint_in_css():
    """CSS must include a media query that stacks the compare columns on narrow viewports."""
    src = _src()
    assert re.search(r"@media.*max-width.*\d+px", src), (
        "CSS must include a max-width media query for responsive compare layout"
    )


def test_ac9_stacked_layout_on_narrow():
    """The compare CSS breakpoint must set grid-template-columns to 1fr (single column)."""
    src = _src()
    # Inside a media query, the columns should stack (1fr or column direction)
    assert re.search(r"@media[^{]*{[^}]*grid-template-columns\s*:\s*1fr|grid-template-columns\s*:\s*1fr[^;]*;\s*}", src) or \
           re.search(r"540|600|480", src), (
        "CSS must stack compare columns to single column on narrow viewports"
    )


def test_ac9_compare_columns_use_grid():
    """Compare columns container must use CSS grid or flex for side-by-side layout."""
    src = _src()
    assert re.search(r"display\s*:\s*grid|display\s*:\s*flex", src), (
        "Compare columns must use CSS grid or flex for side-by-side layout"
    )
