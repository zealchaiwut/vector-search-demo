"""
TDD tests for issue #130: Configurable per-request retrieval pipeline with presets.

AC1 — RetrievalConfig type defined in src/config/retrieval.js with all required fields
AC2 — Default config values read from env vars; every field has a documented env-var name
AC3 — Search endpoint accepts per-request overrides via query params or JSON body
AC4 — Named presets dense-only, hybrid, hybrid-rerank registered as complete RetrievalConfigs
AC5 — Preset selected by name via preset query param; explicit overrides take precedence
AC6 — Search core reads all pipeline decisions from resolved RetrievalConfig
AC7 — Same session, same query, different rerankEnabled → distinct results (or distinct metadata)
AC8 — Invalid preset name → 400 with descriptive error message
AC9 — All config fields covered by unit tests; integration test exercises two configs
"""

import http.client
import json
import os
import re
import socket
import subprocess
import time
import urllib.parse

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RETRIEVAL_CONFIG_JS = os.path.join(REPO_ROOT, "src", "config", "retrieval.js")
SEARCH_INDEX_JS = os.path.join(REPO_ROOT, "src", "search", "index.js")
SERVER_MJS = os.path.join(REPO_ROOT, "src", "server.mjs")

REQUIRED_CONFIG_FIELDS = [
    "embeddingModelId",
    "topK",
    "hybridEnabled",
    "hybridFusionWeight",
    "rerankEnabled",
    "rerankModelId",
    "chunkSize",
    "chunkOverlap",
    "textNormalisationEnabled",
]

KNOWN_PRESETS = ["dense-only", "hybrid", "hybrid-rerank"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_node(script, env=None, timeout=30):
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
        deadline = time.time() + 10
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
        conn = http.client.HTTPConnection("localhost", self.port, timeout=10)
        conn.request("GET", path)
        resp = conn.getresponse()
        body = resp.read()
        conn.close()
        return resp.status, dict(resp.getheaders()), body

    def post(self, path, payload):
        body = json.dumps(payload).encode()
        conn = http.client.HTTPConnection("localhost", self.port, timeout=10)
        conn.request("POST", path, body=body, headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        response_body = resp.read()
        conn.close()
        return resp.status, dict(resp.getheaders()), response_body

    def __exit__(self, *_):
        if self.proc:
            self.proc.terminate()
            self.proc.wait(timeout=3)


# ---------------------------------------------------------------------------
# AC1 — RetrievalConfig file exists and defines all required fields
# ---------------------------------------------------------------------------

def test_ac1_retrieval_config_file_exists():
    assert os.path.isfile(RETRIEVAL_CONFIG_JS), (
        f"src/config/retrieval.js must exist at {RETRIEVAL_CONFIG_JS}"
    )


def test_ac1_retrieval_config_exports_defaultRetrievalConfig():
    with open(RETRIEVAL_CONFIG_JS) as f:
        src = f.read()
    assert "defaultRetrievalConfig" in src, (
        "src/config/retrieval.js must export defaultRetrievalConfig"
    )


def test_ac1_all_required_fields_mentioned_in_source():
    with open(RETRIEVAL_CONFIG_JS) as f:
        src = f.read()
    for field in REQUIRED_CONFIG_FIELDS:
        assert field in src, (
            f"RetrievalConfig field '{field}' must be defined in src/config/retrieval.js"
        )


def test_ac1_defaultRetrievalConfig_returns_all_fields():
    script = """
import { defaultRetrievalConfig } from './src/config/retrieval.js';
const cfg = defaultRetrievalConfig();
process.stdout.write(JSON.stringify(cfg));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    cfg = json.loads(out)
    for field in REQUIRED_CONFIG_FIELDS:
        assert field in cfg, f"defaultRetrievalConfig() missing field '{field}'. Got: {list(cfg.keys())}"


def test_ac1_config_field_types():
    script = """
import { defaultRetrievalConfig } from './src/config/retrieval.js';
const cfg = defaultRetrievalConfig();
const types = Object.fromEntries(Object.entries(cfg).map(([k, v]) => [k, typeof v]));
process.stdout.write(JSON.stringify(types));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    types = json.loads(out)
    assert types["embeddingModelId"] == "string"
    assert types["topK"] == "number"
    assert types["hybridEnabled"] == "boolean"
    assert types["hybridFusionWeight"] == "number"
    assert types["rerankEnabled"] == "boolean"
    assert types["rerankModelId"] == "string"
    assert types["chunkSize"] == "number"
    assert types["chunkOverlap"] == "number"
    assert types["textNormalisationEnabled"] == "boolean"


# ---------------------------------------------------------------------------
# AC2 — Defaults from env vars; documented env-var names
# ---------------------------------------------------------------------------

def test_ac2_env_var_names_documented_in_source():
    with open(RETRIEVAL_CONFIG_JS) as f:
        src = f.read()
    env_vars = [
        "RETRIEVAL_EMBEDDING_MODEL_ID",
        "RETRIEVAL_TOP_K",
        "RETRIEVAL_HYBRID_ENABLED",
        "RETRIEVAL_HYBRID_FUSION_WEIGHT",
        "RETRIEVAL_RERANK_ENABLED",
        "RETRIEVAL_RERANK_MODEL_ID",
        "RETRIEVAL_CHUNK_SIZE",
        "RETRIEVAL_CHUNK_OVERLAP",
        "RETRIEVAL_TEXT_NORMALISATION_ENABLED",
    ]
    for var in env_vars:
        assert var in src, (
            f"Env var '{var}' must be documented/used in src/config/retrieval.js"
        )


def test_ac2_RETRIEVAL_TOP_K_overrides_default_topK():
    script = """
import { defaultRetrievalConfig } from './src/config/retrieval.js';
const cfg = defaultRetrievalConfig();
process.stdout.write(JSON.stringify({ topK: cfg.topK }));
"""
    out, err, rc = _run_node(script, env={"RETRIEVAL_TOP_K": "50"})
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["topK"] == 50, (
        f"RETRIEVAL_TOP_K=50 must set topK=50 in defaults, got {data['topK']}"
    )


def test_ac2_RETRIEVAL_RERANK_ENABLED_true_sets_rerankEnabled():
    script = """
import { defaultRetrievalConfig } from './src/config/retrieval.js';
const cfg = defaultRetrievalConfig();
process.stdout.write(JSON.stringify({ rerankEnabled: cfg.rerankEnabled }));
"""
    out, err, rc = _run_node(script, env={"RETRIEVAL_RERANK_ENABLED": "true"})
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["rerankEnabled"] is True


def test_ac2_RETRIEVAL_HYBRID_ENABLED_true_sets_hybridEnabled():
    script = """
import { defaultRetrievalConfig } from './src/config/retrieval.js';
const cfg = defaultRetrievalConfig();
process.stdout.write(JSON.stringify({ hybridEnabled: cfg.hybridEnabled }));
"""
    out, err, rc = _run_node(script, env={"RETRIEVAL_HYBRID_ENABLED": "true"})
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["hybridEnabled"] is True


def test_ac2_default_rerankEnabled_is_false():
    """rerankEnabled defaults to false when env var is not set."""
    script = """
import { defaultRetrievalConfig } from './src/config/retrieval.js';
const cfg = defaultRetrievalConfig();
process.stdout.write(JSON.stringify({ rerankEnabled: cfg.rerankEnabled }));
"""
    env = {k: v for k, v in os.environ.items() if not k.startswith("RETRIEVAL_")}
    env.pop("RETRIEVAL_RERANK_ENABLED", None)
    out, err, rc = _run_node(script, env=env)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["rerankEnabled"] is False, (
        f"Default rerankEnabled must be false, got {data['rerankEnabled']}"
    )


def test_ac2_default_topK_is_10():
    script = """
import { defaultRetrievalConfig } from './src/config/retrieval.js';
const cfg = defaultRetrievalConfig();
process.stdout.write(JSON.stringify({ topK: cfg.topK }));
"""
    env = {k: v for k, v in os.environ.items() if not k.startswith("RETRIEVAL_")}
    env.pop("RETRIEVAL_TOP_K", None)
    out, err, rc = _run_node(script, env=env)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["topK"] == 10, f"Default topK must be 10, got {data['topK']}"


# ---------------------------------------------------------------------------
# AC3 — Per-request overrides via query params
# ---------------------------------------------------------------------------

def test_ac3_search_rerankEnabled_query_param_reflected_in_response():
    with _ServerProcess() as srv:
        status, _, body = srv.get("/search?q=test&rerankEnabled=true")
    assert status == 200
    data = json.loads(body)
    assert "config" in data, (
        "GET /search response must include a 'config' key with the resolved RetrievalConfig"
    )
    assert data["config"].get("rerankEnabled") is True, (
        "rerankEnabled=true query param must be reflected in response config"
    )


def test_ac3_search_topK_query_param_reflected_in_response():
    with _ServerProcess() as srv:
        status, _, body = srv.get("/search?q=test&topK=5")
    assert status == 200
    data = json.loads(body)
    assert "config" in data
    assert data["config"].get("topK") == 5, (
        f"topK=5 override must appear in response config. Got: {data['config']}"
    )


def test_ac3_search_hybridEnabled_query_param_reflected_in_response():
    with _ServerProcess() as srv:
        status, _, body = srv.get("/search?q=test&hybridEnabled=true")
    assert status == 200
    data = json.loads(body)
    assert "config" in data
    assert data["config"].get("hybridEnabled") is True


def test_ac3_json_body_overrides_accepted():
    """POST /search (or GET with body) with JSON config object overrides are applied."""
    with _ServerProcess() as srv:
        status, _, body = srv.post("/search", {"q": "test", "rerankEnabled": True, "topK": 7})
    assert status == 200, f"Expected 200 for POST /search, got {status}"
    data = json.loads(body)
    assert "config" in data, "POST /search response must include config"
    assert data["config"].get("rerankEnabled") is True
    assert data["config"].get("topK") == 7


# ---------------------------------------------------------------------------
# AC4 — Named presets dense-only, hybrid, hybrid-rerank
# ---------------------------------------------------------------------------

def test_ac4_presets_object_exported_from_retrieval_config():
    with open(RETRIEVAL_CONFIG_JS) as f:
        src = f.read()
    assert "PRESETS" in src or "presets" in src.lower(), (
        "src/config/retrieval.js must export a PRESETS object"
    )
    for name in KNOWN_PRESETS:
        assert name in src, (
            f"Preset '{name}' must be defined in src/config/retrieval.js"
        )


def test_ac4_preset_dense_only_is_complete_config():
    script = """
import { PRESETS } from './src/config/retrieval.js';
process.stdout.write(JSON.stringify(PRESETS['dense-only'] ?? null));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    preset = json.loads(out)
    assert preset is not None, "PRESETS['dense-only'] must exist"
    for field in REQUIRED_CONFIG_FIELDS:
        assert field in preset, f"dense-only preset missing field '{field}'"


def test_ac4_preset_hybrid_is_complete_config():
    script = """
import { PRESETS } from './src/config/retrieval.js';
process.stdout.write(JSON.stringify(PRESETS['hybrid'] ?? null));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    preset = json.loads(out)
    assert preset is not None, "PRESETS['hybrid'] must exist"
    for field in REQUIRED_CONFIG_FIELDS:
        assert field in preset, f"hybrid preset missing field '{field}'"


def test_ac4_preset_hybrid_rerank_is_complete_config():
    script = """
import { PRESETS } from './src/config/retrieval.js';
process.stdout.write(JSON.stringify(PRESETS['hybrid-rerank'] ?? null));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    preset = json.loads(out)
    assert preset is not None, "PRESETS['hybrid-rerank'] must exist"
    for field in REQUIRED_CONFIG_FIELDS:
        assert field in preset, f"hybrid-rerank preset missing field '{field}'"


def test_ac4_dense_only_has_hybrid_false_and_rerank_false():
    script = """
import { PRESETS } from './src/config/retrieval.js';
process.stdout.write(JSON.stringify(PRESETS['dense-only']));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, err
    preset = json.loads(out)
    assert preset["hybridEnabled"] is False, "dense-only must have hybridEnabled=false"
    assert preset["rerankEnabled"] is False, "dense-only must have rerankEnabled=false"


def test_ac4_hybrid_has_hybrid_true_and_rerank_false():
    script = """
import { PRESETS } from './src/config/retrieval.js';
process.stdout.write(JSON.stringify(PRESETS['hybrid']));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, err
    preset = json.loads(out)
    assert preset["hybridEnabled"] is True, "hybrid preset must have hybridEnabled=true"
    assert preset["rerankEnabled"] is False, "hybrid preset must have rerankEnabled=false"


def test_ac4_hybrid_rerank_has_hybrid_true_and_rerank_true():
    script = """
import { PRESETS } from './src/config/retrieval.js';
process.stdout.write(JSON.stringify(PRESETS['hybrid-rerank']));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, err
    preset = json.loads(out)
    assert preset["hybridEnabled"] is True, "hybrid-rerank must have hybridEnabled=true"
    assert preset["rerankEnabled"] is True, "hybrid-rerank must have rerankEnabled=true"


# ---------------------------------------------------------------------------
# AC5 — Preset selected by name; explicit overrides beat preset
# ---------------------------------------------------------------------------

def test_ac5_preset_hybrid_rerank_applied_via_query_param():
    with _ServerProcess() as srv:
        status, _, body = srv.get("/search?q=test&preset=hybrid-rerank")
    assert status == 200, f"Expected 200, got {status}"
    data = json.loads(body)
    assert "config" in data, "Response must include config when preset is selected"
    cfg = data["config"]
    assert cfg.get("hybridEnabled") is True, (
        f"hybrid-rerank preset must set hybridEnabled=true in response config. Got: {cfg}"
    )
    assert cfg.get("rerankEnabled") is True, (
        f"hybrid-rerank preset must set rerankEnabled=true in response config. Got: {cfg}"
    )


def test_ac5_preset_dense_only_applied_via_query_param():
    with _ServerProcess() as srv:
        status, _, body = srv.get("/search?q=test&preset=dense-only")
    assert status == 200
    data = json.loads(body)
    cfg = data["config"]
    assert cfg.get("hybridEnabled") is False
    assert cfg.get("rerankEnabled") is False


def test_ac5_explicit_override_beats_preset():
    """preset=hybrid-rerank + rerankEnabled=false → rerankEnabled must be false."""
    with _ServerProcess() as srv:
        status, _, body = srv.get("/search?q=test&preset=hybrid-rerank&rerankEnabled=false")
    assert status == 200
    data = json.loads(body)
    cfg = data["config"]
    assert cfg.get("rerankEnabled") is False, (
        f"Explicit rerankEnabled=false must override hybrid-rerank preset. Got: {cfg}"
    )
    assert cfg.get("hybridEnabled") is True, (
        "Other preset fields must remain intact when only one field is overridden"
    )


def test_ac5_resolveRetrievalConfig_node_level():
    script = """
import { resolveRetrievalConfig } from './src/config/retrieval.js';
const { config, error } = resolveRetrievalConfig('hybrid-rerank', { rerankEnabled: false });
process.stdout.write(JSON.stringify({ config, error }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    result = json.loads(out)
    assert result["error"] is None
    cfg = result["config"]
    assert cfg["rerankEnabled"] is False, "Explicit override must beat preset"
    assert cfg["hybridEnabled"] is True, "Non-overridden preset field must remain"


# ---------------------------------------------------------------------------
# AC6 — Search core reads from RetrievalConfig
# ---------------------------------------------------------------------------

def test_ac6_search_index_imports_retrieval_config():
    with open(SEARCH_INDEX_JS) as f:
        src = f.read()
    assert "retrieval" in src.lower() or "RetrievalConfig" in src or "resolveRetrievalConfig" in src, (
        "src/search/index.js must import/use RetrievalConfig from src/config/retrieval.js"
    )


def test_ac6_searchDocuments_accepts_config_param():
    with open(SEARCH_INDEX_JS) as f:
        src = f.read()
    assert re.search(r"searchDocuments\s*\([^)]*[Cc]onfig", src), (
        "searchDocuments must accept a config/retrievalConfig parameter"
    )


def test_ac6_no_hardcoded_rerankEnabled_flag():
    with open(SEARCH_INDEX_JS) as f:
        src = f.read()
    assert not re.search(r"rerankEnabled\s*=\s*(true|false)", src), (
        "src/search/index.js must not hardcode rerankEnabled; read it from config"
    )


def test_ac6_no_hardcoded_hybridEnabled_flag():
    with open(SEARCH_INDEX_JS) as f:
        src = f.read()
    assert not re.search(r"hybridEnabled\s*=\s*(true|false)", src), (
        "src/search/index.js must not hardcode hybridEnabled; read it from config"
    )


# ---------------------------------------------------------------------------
# AC7 — Same session, different configs → distinct result sets (or metadata)
# ---------------------------------------------------------------------------

def test_ac7_rerankEnabled_true_vs_false_different_metadata():
    with _ServerProcess() as srv:
        _, _, body_rerank = srv.get("/search?q=test&rerankEnabled=true")
        _, _, body_no_rerank = srv.get("/search?q=test&rerankEnabled=false")

    data_rerank = json.loads(body_rerank)
    data_no_rerank = json.loads(body_no_rerank)

    assert "config" in data_rerank, "Response must include config"
    assert "config" in data_no_rerank, "Response must include config"

    assert data_rerank["config"].get("rerankEnabled") is True
    assert data_no_rerank["config"].get("rerankEnabled") is False


def test_ac7_no_restart_needed_between_config_changes():
    """Both requests succeed in the same server session without restart."""
    with _ServerProcess() as srv:
        s1, _, b1 = srv.get("/search?q=vector&rerankEnabled=true")
        s2, _, b2 = srv.get("/search?q=vector&rerankEnabled=false")
    assert s1 == 200, f"First request failed: {s1}"
    assert s2 == 200, f"Second request failed: {s2}"
    d1 = json.loads(b1)
    d2 = json.loads(b2)
    assert d1["config"]["rerankEnabled"] is True
    assert d2["config"]["rerankEnabled"] is False


# ---------------------------------------------------------------------------
# AC8 — Invalid preset → 400 with descriptive error
# ---------------------------------------------------------------------------

def test_ac8_invalid_preset_returns_400():
    with _ServerProcess() as srv:
        status, _, body = srv.get("/search?q=test&preset=nonexistent")
    assert status == 400, (
        f"Invalid preset must return HTTP 400, got {status}. Body: {body[:200]}"
    )


def test_ac8_error_message_names_unrecognised_preset():
    with _ServerProcess() as srv:
        status, _, body = srv.get("/search?q=test&preset=bad-preset-xyz")
    assert status == 400
    data = json.loads(body)
    err_text = json.dumps(data).lower()
    assert "bad-preset-xyz" in err_text or "preset" in err_text, (
        f"400 error message must mention the bad preset name. Got: {data}"
    )


def test_ac8_resolveRetrievalConfig_returns_error_for_unknown():
    script = """
import { resolveRetrievalConfig } from './src/config/retrieval.js';
const { config, error } = resolveRetrievalConfig('nonexistent-preset');
process.stdout.write(JSON.stringify({ config, error }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    result = json.loads(out)
    assert result["error"] is not None, "resolveRetrievalConfig must return an error for unknown presets"
    assert result["config"] is None, "config must be null when preset is unknown"
    assert "nonexistent-preset" in result["error"] or "preset" in result["error"].lower()


# ---------------------------------------------------------------------------
# AC9 — Unit tests cover all config fields; integration test exercises two configs
# ---------------------------------------------------------------------------

def test_ac9_parseConfigOverrides_coerces_string_booleans():
    script = """
import { parseConfigOverrides } from './src/config/retrieval.js';
const out = parseConfigOverrides({
  rerankEnabled: 'true',
  hybridEnabled: 'false',
  topK: '25',
  hybridFusionWeight: '0.3',
});
process.stdout.write(JSON.stringify(out));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    result = json.loads(out)
    assert result["rerankEnabled"] is True
    assert result["hybridEnabled"] is False
    assert result["topK"] == 25
    assert abs(result["hybridFusionWeight"] - 0.3) < 1e-9


def test_ac9_parseConfigOverrides_ignores_unknown_keys():
    script = """
import { parseConfigOverrides } from './src/config/retrieval.js';
const out = parseConfigOverrides({ rerankEnabled: 'true', unknownField: 'xyz' });
process.stdout.write(JSON.stringify(out));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    result = json.loads(out)
    assert "unknownField" not in result, "parseConfigOverrides must ignore unknown keys"
    assert result.get("rerankEnabled") is True


def test_ac9_resolveRetrievalConfig_env_topK_overridden_by_query_param():
    """Integration: RETRIEVAL_TOP_K=50 in env, but topK=10 override → topK=10 wins."""
    script = """
import { resolveRetrievalConfig, parseConfigOverrides } from './src/config/retrieval.js';
const overrides = parseConfigOverrides({ topK: '10' });
const { config } = resolveRetrievalConfig(null, overrides);
process.stdout.write(JSON.stringify({ topK: config.topK }));
"""
    out, err, rc = _run_node(script, env={"RETRIEVAL_TOP_K": "50"})
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["topK"] == 10, (
        f"Per-request topK=10 must override RETRIEVAL_TOP_K=50. Got: {data['topK']}"
    )


def test_ac9_integration_two_configs_same_live_server():
    """Integration: hit the live /search endpoint twice with different configs."""
    with _ServerProcess() as srv:
        s1, _, b1 = srv.get("/search?q=machine+learning&topK=5")
        s2, _, b2 = srv.get("/search?q=machine+learning&topK=3&rerankEnabled=true")

    assert s1 == 200 and s2 == 200

    d1 = json.loads(b1)
    d2 = json.loads(b2)

    assert d1["config"]["topK"] == 5
    assert d2["config"]["topK"] == 3
    assert d2["config"]["rerankEnabled"] is True
    assert d1["config"]["rerankEnabled"] is False or d1["config"].get("rerankEnabled") != True


def test_ac9_env_RETRIEVAL_TOP_K_reflected_in_live_server():
    """RETRIEVAL_TOP_K=50 env var must appear in the default config of a live server."""
    with _ServerProcess(env={"RETRIEVAL_TOP_K": "50"}) as srv:
        status, _, body = srv.get("/search?q=test")
    assert status == 200
    data = json.loads(body)
    assert "config" in data
    assert data["config"]["topK"] == 50, (
        f"Server started with RETRIEVAL_TOP_K=50 must reflect topK=50 in config. Got: {data['config']}"
    )


def test_ac9_per_request_topK_beats_env_on_live_server():
    """topK=10 query param wins over RETRIEVAL_TOP_K=50 env var on live server."""
    with _ServerProcess(env={"RETRIEVAL_TOP_K": "50"}) as srv:
        status, _, body = srv.get("/search?q=test&topK=10")
    assert status == 200
    data = json.loads(body)
    assert data["config"]["topK"] == 10, (
        f"Per-request topK=10 must beat RETRIEVAL_TOP_K=50 env. Got: {data['config']}"
    )
