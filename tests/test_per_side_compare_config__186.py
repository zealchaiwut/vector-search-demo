"""
TDD tests for issue #186: Add independent per-side config to Compare tab.

AC1 — The Compare tab exposes an embedding model selector and a mode selector
       (semantic / keyword / hybrid) for both the left and right panels independently.
AC2 — Submitting a query executes two separate searches — one per side — using
       each panel's selected model and mode.
AC3 — Both result lists are displayed side by side, each showing ranked results
       with their individual scores.
AC4 — Changing the model or mode on either side re-runs that side's search
       immediately without a full page reload.
AC5 — The left and right panels can be set to the same or different models and
       modes simultaneously.
AC6 — src/search accepts a per-side config object that carries at minimum the
       embedding model identifier and the search mode.
AC7 — Score values are visible per result on each side (e.g. displayed as a
       numeric badge or label).
AC8 — Panel state (selected model and mode) persists across query re-runs within
       the same session.
"""

import http.client
import json
import os
import re
import socket
import subprocess
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_HTML = os.path.join(REPO_ROOT, "public", "index.html")
SERVER_MJS = os.path.join(REPO_ROOT, "src", "server.mjs")
RETRIEVAL_CONFIG_JS = os.path.join(REPO_ROOT, "src", "config", "retrieval.js")
MODEL_REGISTRY_JS = os.path.join(REPO_ROOT, "src", "embeddings", "model-registry.js")


def _src():
    with open(INDEX_HTML) as f:
        return f.read()


def _server_src():
    with open(SERVER_MJS) as f:
        return f.read()


def _retrieval_src():
    with open(RETRIEVAL_CONFIG_JS) as f:
        return f.read()


def _model_registry_src():
    with open(MODEL_REGISTRY_JS) as f:
        return f.read()


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
        conn.request(
            "POST", path, body=body, headers={"Content-Type": "application/json"}
        )
        resp = conn.getresponse()
        response_body = resp.read()
        conn.close()
        return resp.status, dict(resp.getheaders()), response_body

    def __exit__(self, *_):
        if self.proc:
            self.proc.terminate()
            self.proc.wait(timeout=5)


# ---------------------------------------------------------------------------
# AC1 — Model selector and mode selector per panel
# ---------------------------------------------------------------------------


def test_ac1_left_panel_has_model_selector():
    """AC1: Compare tab must have an embedding model selector for the left panel."""
    src = _src()
    # Look for a model selector element scoped to left/A panel
    assert re.search(r'id=["\']model-a["\']', src) or re.search(
        r'id=["\']model-sel-a["\']', src
    ), "Compare tab must have a model selector for the left panel (id=model-a or model-sel-a)"


def test_ac1_right_panel_has_model_selector():
    """AC1: Compare tab must have an embedding model selector for the right panel."""
    src = _src()
    assert re.search(r'id=["\']model-b["\']', src) or re.search(
        r'id=["\']model-sel-b["\']', src
    ), "Compare tab must have a model selector for the right panel (id=model-b or model-sel-b)"


def test_ac1_left_panel_has_mode_selector():
    """AC1: Compare tab must have a search mode selector for the left panel."""
    src = _src()
    assert re.search(r'id=["\']mode-a["\']', src) or re.search(
        r'id=["\']mode-sel-a["\']', src
    ), "Compare tab must have a mode selector for the left panel (id=mode-a or mode-sel-a)"


def test_ac1_right_panel_has_mode_selector():
    """AC1: Compare tab must have a search mode selector for the right panel."""
    src = _src()
    assert re.search(r'id=["\']mode-b["\']', src) or re.search(
        r'id=["\']mode-sel-b["\']', src
    ), "Compare tab must have a mode selector for the right panel (id=mode-b or mode-sel-b)"


def test_ac1_mode_selector_has_semantic_option():
    """AC1: The mode selector must include a 'semantic' option."""
    src = _src()
    assert re.search(r'value=["\']semantic["\']', src), (
        "Mode selectors must include a 'semantic' option"
    )


def test_ac1_mode_selector_has_keyword_option():
    """AC1: The mode selector must include a 'keyword' option."""
    src = _src()
    assert re.search(r'value=["\']keyword["\']', src), (
        "Mode selectors must include a 'keyword' option"
    )


def test_ac1_mode_selector_has_hybrid_option():
    """AC1: The mode selector must include a 'hybrid' option."""
    src = _src()
    assert re.search(r'value=["\']hybrid["\']', src), (
        "Mode selectors must include a 'hybrid' option"
    )


def test_ac1_model_selectors_are_select_elements():
    """AC1: The model selectors must be <select> elements."""
    src = _src()
    assert re.search(r'<select[^>]+id=["\']model-[ab]["\']', src), (
        "Model selectors must be <select> elements with id=model-a / model-b"
    )


def test_ac1_mode_selectors_are_select_elements():
    """AC1: The mode selectors must be <select> elements."""
    src = _src()
    assert re.search(r'<select[^>]+id=["\']mode-[ab]["\']', src), (
        "Mode selectors must be <select> elements with id=mode-a / mode-b"
    )


def test_ac1_api_models_endpoint_in_server():
    """AC1: server.mjs must expose a GET /api/models endpoint."""
    src = _server_src()
    assert re.search(r"/api/models", src), (
        "server.mjs must handle GET /api/models to return available embedding models"
    )


def test_ac1_api_models_returns_model_list():
    """AC1: GET /api/models must return a JSON object with a models array."""
    with _ServerProcess() as srv:
        status, _, body = srv.get("/api/models")
    assert status == 200, f"Expected 200, got {status}"
    data = json.loads(body)
    assert "models" in data, f"Response must have 'models' key. Got: {list(data.keys())}"
    assert isinstance(data["models"], list), "models must be an array"
    assert len(data["models"]) > 0, "models must not be empty"


def test_ac1_api_models_includes_model_ids():
    """AC1: GET /api/models must include at least one valid model id."""
    with _ServerProcess() as srv:
        status, _, body = srv.get("/api/models")
    assert status == 200
    data = json.loads(body)
    models = data["models"]
    ids = [m["id"] if isinstance(m, dict) else m for m in models]
    known = {
        "Xenova/multilingual-e5-small",
        "multilingual-e5-small",
        "BAAI/bge-m3",
        "Xenova/all-MiniLM-L6-v2",
    }
    assert any(mid in known for mid in ids), (
        f"GET /api/models must include at least one known model id. Got: {ids}"
    )


def test_ac1_js_loads_models_from_api():
    """AC1: Frontend JS must call /api/models to populate model dropdowns."""
    src = _src()
    assert re.search(r"/api/models", src), (
        "Compare tab JS must call /api/models to populate model selectors"
    )


# ---------------------------------------------------------------------------
# AC2 — Two separate searches using each panel's model and mode
# ---------------------------------------------------------------------------


def test_ac2_js_uses_embedding_model_param():
    """AC2: Search requests must include the selected embedding model identifier."""
    src = _src()
    assert re.search(
        r"embeddingModelId|embedding_model|model.*search|search.*model", src, re.IGNORECASE
    ), "JS must pass the selected embedding model to search requests"


def test_ac2_js_uses_mode_param():
    """AC2: Search requests must include the selected mode (semantic/keyword/hybrid)."""
    src = _src()
    assert re.search(
        r"searchMode|search.mode|mode.*search|hybridEnabled|hybrid.*enabled", src, re.IGNORECASE
    ), "JS must pass the selected mode to search requests"


def test_ac2_js_uses_promise_all_for_parallel():
    """AC2: JS must use Promise.all to fire both panel searches in parallel."""
    src = _src()
    assert re.search(r"Promise\.all", src), (
        "Compare tab JS must use Promise.all to fire panel A and B searches in parallel"
    )


def test_ac2_search_accepts_embedding_model_param():
    """AC2: GET /search must accept embeddingModelId parameter without error."""
    with _ServerProcess() as srv:
        status, _, body = srv.get(
            "/search?q=test&embeddingModelId=Xenova%2Fall-MiniLM-L6-v2&debug=true"
        )
    assert status == 200, f"Expected 200, got {status}. Body: {body[:300]}"
    data = json.loads(body)
    assert "results" in data


def test_ac2_keyword_mode_routes_to_exact_search():
    """AC2: When mode=keyword, the frontend calls /search/exact or server routes to exact search."""
    src = _src()
    # Frontend should have logic to call /search/exact for keyword mode
    assert re.search(r"search/exact|searchExact|mode.*keyword|keyword.*exact", src, re.IGNORECASE), (
        "JS must route keyword mode to /search/exact or equivalent"
    )


# ---------------------------------------------------------------------------
# AC3 — Side-by-side results with individual scores
# ---------------------------------------------------------------------------


def test_ac3_compare_columns_side_by_side():
    """AC3: Compare columns must be displayed side by side (CSS grid/flex)."""
    src = _src()
    assert re.search(r"grid-template-columns.*1fr.*1fr|1fr 1fr", src), (
        "Compare columns must use a two-column layout (1fr 1fr grid)"
    )


def test_ac3_score_displayed_per_result():
    """AC3: Each result card must display a score value."""
    src = _src()
    # Check that the JS renders a score field from results
    assert re.search(r"\.score|score.*toFixed|score.*badge|score.*label", src, re.IGNORECASE), (
        "Compare result cards must display the score for each result"
    )


def test_ac3_two_result_containers():
    """AC3: There must be two separate result containers (one per panel)."""
    src = _src()
    count = len(re.findall(r'compare-results|compare-col\b', src))
    assert count >= 2, (
        f"Compare panel must have at least two result containers. Found {count} matches"
    )


# ---------------------------------------------------------------------------
# AC4 — Changing model or mode re-runs that side's search immediately
# ---------------------------------------------------------------------------


def test_ac4_model_a_change_listener():
    """AC4: JS must add a 'change' listener on the left panel's model selector."""
    src = _src()
    assert re.search(
        r"model-a.*change|modelA.*change|model.*[Ss]elect.*change.*a|addEventListener.*change.*model", src
    ) or re.search(
        r'model.a.*addEventListener|addEventListener.*change.*model.a', src
    ) or re.search(
        r"modelASelect.*change|modelSelA.*change|modelA.*addEventListener", src
    ), "JS must listen for 'change' events on the left panel's model selector"


def test_ac4_mode_a_change_listener():
    """AC4: JS must add a 'change' listener on the left panel's mode selector."""
    src = _src()
    assert re.search(
        r"mode-a.*change|modeA.*change|mode.*Select.*change|addEventListener.*change.*mode", src
    ) or re.search(
        r"modeASelect.*change|modeSel.*change", src
    ), "JS must listen for 'change' events on the left panel's mode selector"


def test_ac4_model_b_change_listener():
    """AC4: JS must add a 'change' listener on the right panel's model selector."""
    src = _src()
    assert re.search(
        r"model-b.*change|modelB.*change|model.*[Ss]elect.*change.*b|modelBSelect.*change", src
    ) or re.search(
        r"modelBSelect.*change|modelSelB.*change", src
    ), "JS must listen for 'change' events on the right panel's model selector"


def test_ac4_mode_b_change_listener():
    """AC4: JS must add a 'change' listener on the right panel's mode selector."""
    src = _src()
    assert re.search(
        r"mode-b.*change|modeB.*change|modeBSelect.*change|modeSelB.*change", src
    ), "JS must listen for 'change' events on the right panel's mode selector"


def test_ac4_no_page_reload_on_change():
    """AC4: JS must not reload the page when model or mode changes."""
    src = _src()
    assert not re.search(r"window\.location\.reload\(\)|location\.reload\(\)", src), (
        "JS must not call location.reload() — only the affected panel should re-run"
    )


def test_ac4_change_reruns_only_one_column():
    """AC4: The change handler must call a per-column search, not both columns."""
    src = _src()
    assert re.search(r"runColSearch|searchCol|runSearch", src, re.IGNORECASE), (
        "JS must have a per-column search function invoked from the change handlers"
    )


# ---------------------------------------------------------------------------
# AC5 — Panels can use the same or different models and modes
# ---------------------------------------------------------------------------


def test_ac5_model_selectors_are_independent():
    """AC5: Left and right model selectors must be separate DOM elements."""
    src = _src()
    # Both id=model-a and id=model-b (or similar) must exist
    has_a = bool(re.search(r'id=["\']model-a["\']', src))
    has_b = bool(re.search(r'id=["\']model-b["\']', src))
    assert has_a and has_b, (
        "Left and right panels must each have their own independent model selector element"
    )


def test_ac5_mode_selectors_are_independent():
    """AC5: Left and right mode selectors must be separate DOM elements."""
    src = _src()
    has_a = bool(re.search(r'id=["\']mode-a["\']', src))
    has_b = bool(re.search(r'id=["\']mode-b["\']', src))
    assert has_a and has_b, (
        "Left and right panels must each have their own independent mode selector element"
    )


# ---------------------------------------------------------------------------
# AC6 — src/search accepts a per-side config object with embeddingModelId and searchMode
# ---------------------------------------------------------------------------


def test_ac6_retrieval_config_parses_search_mode():
    """AC6: parseConfigOverrides must recognise the searchMode parameter."""
    src = _retrieval_src()
    assert re.search(r"searchMode", src), (
        "parseConfigOverrides in retrieval.js must handle the 'searchMode' parameter"
    )


def test_ac6_search_mode_maps_to_hybrid_enabled():
    """AC6: searchMode='hybrid' in config must set hybridEnabled=true."""
    src = _retrieval_src()
    # The code should map mode values to hybridEnabled
    assert re.search(r"hybrid.*hybridEnabled|hybridEnabled.*hybrid|searchMode.*hybrid", src, re.IGNORECASE), (
        "retrieval.js must map searchMode='hybrid' to hybridEnabled=true"
    )


def test_ac6_search_mode_semantic_maps_to_dense_only():
    """AC6: searchMode='semantic' in config must set hybridEnabled=false."""
    src = _retrieval_src()
    assert re.search(r"semantic.*hybridEnabled.*false|hybridEnabled.*false.*semantic|searchMode.*semantic", src, re.IGNORECASE), (
        "retrieval.js must map searchMode='semantic' to hybridEnabled=false"
    )


def test_ac6_retrieval_config_includes_embedding_model_id():
    """AC6: The retrieval config must include an embeddingModelId field."""
    src = _retrieval_src()
    assert re.search(r"embeddingModelId", src), (
        "retrieval.js config must include embeddingModelId to identify the embedding model"
    )


def test_ac6_server_passes_embedding_model_to_search():
    """AC6: server.mjs must pass embeddingModelId from request params to searchDocuments."""
    src = _server_src()
    assert re.search(r"embeddingModelId|parseConfigOverrides", src), (
        "server.mjs must extract and pass embeddingModelId to the search pipeline"
    )


def test_ac6_search_accepts_mode_via_api():
    """AC6: GET /search?searchMode=semantic must return 200 with results."""
    with _ServerProcess() as srv:
        status, _, body = srv.get(
            "/search?q=test&searchMode=semantic&embeddingModelId=Xenova%2Fall-MiniLM-L6-v2"
        )
    assert status == 200, f"Expected 200, got {status}. Body: {body[:300]}"
    data = json.loads(body)
    assert "results" in data


def test_ac6_search_accepts_hybrid_mode_via_api():
    """AC6: GET /search?searchMode=hybrid must return 200 with results."""
    with _ServerProcess() as srv:
        status, _, body = srv.get(
            "/search?q=test&searchMode=hybrid&embeddingModelId=Xenova%2Fall-MiniLM-L6-v2"
        )
    assert status == 200, f"Expected 200, got {status}. Body: {body[:300]}"
    data = json.loads(body)
    assert "results" in data


# ---------------------------------------------------------------------------
# AC7 — Score values visible per result
# ---------------------------------------------------------------------------


def test_ac7_js_renders_score_in_compare_cards():
    """AC7: JS must render a numeric score on each compare result card."""
    src = _src()
    # The renderCompareCard or equivalent function must include score display
    assert re.search(
        r"score.*toFixed|toFixed.*score|explain.*score|score.*badge|\.score\b", src
    ), "Compare result cards must display the numeric score for each result"


def test_ac7_score_css_class_exists():
    """AC7: HTML/CSS must include a style for score badges or labels."""
    src = _src()
    assert re.search(
        r"explain-stage|score-badge|score-label|\.score\b", src
    ), "HTML must define a CSS class for score display (e.g. explain-stage or score-badge)"


def test_ac7_api_results_include_score_field():
    """AC7: Search API must return a score field on each result for the frontend to display."""
    with _ServerProcess() as srv:
        status, _, body = srv.get("/search?q=test&debug=true")
    assert status == 200
    data = json.loads(body)
    for r in data.get("results", []):
        assert "score" in r or "explain" in r, (
            f"Each search result must have a 'score' or 'explain' field. Got: {list(r.keys())}"
        )


# ---------------------------------------------------------------------------
# AC8 — Panel state persists across query re-runs within the session
# ---------------------------------------------------------------------------


def test_ac8_panel_state_in_js_variables():
    """AC8: JS must track model/mode selections in variables (not only in DOM)."""
    src = _src()
    # Check for JS variables that store model/mode state per panel
    assert re.search(
        r"modelA|modelB|modeA|modeB|model_a|model_b|mode_a|mode_b|"
        r"modelASelect|modelBSelect|modeASelect|modeBSelect",
        src,
    ), "JS must store panel model/mode state in variables accessible across re-runs"


def test_ac8_query_rerun_uses_current_selectors():
    """AC8: Re-running a query must use the currently selected model and mode, not a stale value."""
    src = _src()
    # The doCompare function or equivalent must read model/mode from select elements at call time
    assert re.search(
        r"\.value.*embeddingModelId|embeddingModelId.*\.value|modelA.*\.value|modelB.*\.value|"
        r"modeA.*\.value|modeB.*\.value",
        src,
    ) or re.search(
        r"modelASelect\.value|modelBSelect\.value|modeASelect\.value|modeBSelect\.value", src
    ), "JS must read model/mode from the selector elements at query time (not cache stale values)"
