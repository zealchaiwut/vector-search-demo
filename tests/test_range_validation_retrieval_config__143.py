"""
TDD tests for issue #143: Range validation for numeric RetrievalConfig overrides.

AC — parseConfigOverrides / resolveRetrievalConfig must reject out-of-range values:
  AC1 — topK must be in [1, 500]; values outside that range return a descriptive error
  AC2 — hybridFusionWeight must be in [0.0, 1.0]; values outside return a descriptive error
  AC3 — Valid boundary values (1, 500, 0.0, 1.0) are accepted without error
  AC4 — HTTP /search endpoint returns 400 with descriptive message for out-of-range topK
  AC5 — HTTP /search endpoint returns 400 with descriptive message for out-of-range hybridFusionWeight
  AC6 — Error messages name the field and the allowed range
"""

import http.client
import json
import os
import socket
import subprocess
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RETRIEVAL_CONFIG_JS = os.path.join(REPO_ROOT, "src", "config", "retrieval.js")
SERVER_MJS = os.path.join(REPO_ROOT, "src", "server.mjs")


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

    def __exit__(self, *_):
        if self.proc:
            self.proc.terminate()
            self.proc.wait(timeout=3)


# ---------------------------------------------------------------------------
# AC1 — topK must be in [1, 500]
# ---------------------------------------------------------------------------

def test_ac1_topK_zero_returns_error():
    script = """
import { resolveRetrievalConfig, parseConfigOverrides } from './src/config/retrieval.js';
const overrides = parseConfigOverrides({ topK: '0' });
const { config, error } = resolveRetrievalConfig(null, overrides);
process.stdout.write(JSON.stringify({ config, error }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    result = json.loads(out)
    assert result["error"] is not None, "topK=0 must return an error"
    assert result["config"] is None, "config must be null when topK is out of range"


def test_ac1_topK_negative_returns_error():
    script = """
import { resolveRetrievalConfig, parseConfigOverrides } from './src/config/retrieval.js';
const overrides = parseConfigOverrides({ topK: '-1' });
const { config, error } = resolveRetrievalConfig(null, overrides);
process.stdout.write(JSON.stringify({ config, error }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    result = json.loads(out)
    assert result["error"] is not None, "topK=-1 must return an error"
    assert result["config"] is None


def test_ac1_topK_above_500_returns_error():
    script = """
import { resolveRetrievalConfig, parseConfigOverrides } from './src/config/retrieval.js';
const overrides = parseConfigOverrides({ topK: '501' });
const { config, error } = resolveRetrievalConfig(null, overrides);
process.stdout.write(JSON.stringify({ config, error }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    result = json.loads(out)
    assert result["error"] is not None, "topK=501 must return an error"
    assert result["config"] is None


# ---------------------------------------------------------------------------
# AC2 — hybridFusionWeight must be in [0.0, 1.0]
# ---------------------------------------------------------------------------

def test_ac2_hybridFusionWeight_above_1_returns_error():
    script = """
import { resolveRetrievalConfig, parseConfigOverrides } from './src/config/retrieval.js';
const overrides = parseConfigOverrides({ hybridFusionWeight: '5.0' });
const { config, error } = resolveRetrievalConfig(null, overrides);
process.stdout.write(JSON.stringify({ config, error }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    result = json.loads(out)
    assert result["error"] is not None, "hybridFusionWeight=5.0 must return an error"
    assert result["config"] is None


def test_ac2_hybridFusionWeight_negative_returns_error():
    script = """
import { resolveRetrievalConfig, parseConfigOverrides } from './src/config/retrieval.js';
const overrides = parseConfigOverrides({ hybridFusionWeight: '-0.1' });
const { config, error } = resolveRetrievalConfig(null, overrides);
process.stdout.write(JSON.stringify({ config, error }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    result = json.loads(out)
    assert result["error"] is not None, "hybridFusionWeight=-0.1 must return an error"
    assert result["config"] is None


def test_ac2_hybridFusionWeight_slightly_above_1_returns_error():
    script = """
import { resolveRetrievalConfig, parseConfigOverrides } from './src/config/retrieval.js';
const overrides = parseConfigOverrides({ hybridFusionWeight: '1.01' });
const { config, error } = resolveRetrievalConfig(null, overrides);
process.stdout.write(JSON.stringify({ config, error }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    result = json.loads(out)
    assert result["error"] is not None, "hybridFusionWeight=1.01 must return an error"
    assert result["config"] is None


# ---------------------------------------------------------------------------
# AC3 — Valid boundary values are accepted
# ---------------------------------------------------------------------------

def test_ac3_topK_1_is_valid():
    script = """
import { resolveRetrievalConfig, parseConfigOverrides } from './src/config/retrieval.js';
const overrides = parseConfigOverrides({ topK: '1' });
const { config, error } = resolveRetrievalConfig(null, overrides);
process.stdout.write(JSON.stringify({ config: config ? { topK: config.topK } : null, error }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    result = json.loads(out)
    assert result["error"] is None, f"topK=1 must be valid, got error: {result['error']}"
    assert result["config"]["topK"] == 1


def test_ac3_topK_500_is_valid():
    script = """
import { resolveRetrievalConfig, parseConfigOverrides } from './src/config/retrieval.js';
const overrides = parseConfigOverrides({ topK: '500' });
const { config, error } = resolveRetrievalConfig(null, overrides);
process.stdout.write(JSON.stringify({ config: config ? { topK: config.topK } : null, error }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    result = json.loads(out)
    assert result["error"] is None, f"topK=500 must be valid, got error: {result['error']}"
    assert result["config"]["topK"] == 500


def test_ac3_hybridFusionWeight_0_is_valid():
    script = """
import { resolveRetrievalConfig, parseConfigOverrides } from './src/config/retrieval.js';
const overrides = parseConfigOverrides({ hybridFusionWeight: '0.0' });
const { config, error } = resolveRetrievalConfig(null, overrides);
process.stdout.write(JSON.stringify({ config: config ? { hybridFusionWeight: config.hybridFusionWeight } : null, error }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    result = json.loads(out)
    assert result["error"] is None, f"hybridFusionWeight=0.0 must be valid, got error: {result['error']}"
    assert result["config"]["hybridFusionWeight"] == 0.0


def test_ac3_hybridFusionWeight_1_is_valid():
    script = """
import { resolveRetrievalConfig, parseConfigOverrides } from './src/config/retrieval.js';
const overrides = parseConfigOverrides({ hybridFusionWeight: '1.0' });
const { config, error } = resolveRetrievalConfig(null, overrides);
process.stdout.write(JSON.stringify({ config: config ? { hybridFusionWeight: config.hybridFusionWeight } : null, error }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    result = json.loads(out)
    assert result["error"] is None, f"hybridFusionWeight=1.0 must be valid, got error: {result['error']}"
    assert abs(result["config"]["hybridFusionWeight"] - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# AC4 — HTTP /search returns 400 for out-of-range topK
# ---------------------------------------------------------------------------

def test_ac4_http_topK_zero_returns_400():
    with _ServerProcess() as srv:
        status, _, body = srv.get("/search?q=test&topK=0")
    assert status == 400, f"topK=0 via HTTP must return 400, got {status}. Body: {body[:200]}"


def test_ac4_http_topK_negative_returns_400():
    with _ServerProcess() as srv:
        status, _, body = srv.get("/search?q=test&topK=-1")
    assert status == 400, f"topK=-1 via HTTP must return 400, got {status}. Body: {body[:200]}"


def test_ac4_http_topK_501_returns_400():
    with _ServerProcess() as srv:
        status, _, body = srv.get("/search?q=test&topK=501")
    assert status == 400, f"topK=501 via HTTP must return 400, got {status}. Body: {body[:200]}"


# ---------------------------------------------------------------------------
# AC5 — HTTP /search returns 400 for out-of-range hybridFusionWeight
# ---------------------------------------------------------------------------

def test_ac5_http_hybridFusionWeight_above_1_returns_400():
    with _ServerProcess() as srv:
        status, _, body = srv.get("/search?q=test&hybridFusionWeight=5.0")
    assert status == 400, (
        f"hybridFusionWeight=5.0 via HTTP must return 400, got {status}. Body: {body[:200]}"
    )


def test_ac5_http_hybridFusionWeight_negative_returns_400():
    with _ServerProcess() as srv:
        status, _, body = srv.get("/search?q=test&hybridFusionWeight=-0.5")
    assert status == 400, (
        f"hybridFusionWeight=-0.5 via HTTP must return 400, got {status}. Body: {body[:200]}"
    )


# ---------------------------------------------------------------------------
# AC6 — Error messages name the field and the allowed range
# ---------------------------------------------------------------------------

def test_ac6_topK_error_mentions_field_and_range():
    script = """
import { resolveRetrievalConfig, parseConfigOverrides } from './src/config/retrieval.js';
const overrides = parseConfigOverrides({ topK: '0' });
const { config, error } = resolveRetrievalConfig(null, overrides);
process.stdout.write(JSON.stringify({ error }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    result = json.loads(out)
    error_text = (result["error"] or "").lower()
    assert "topk" in error_text or "top_k" in error_text or "top-k" in error_text, (
        f"Error message must mention 'topK'. Got: {result['error']}"
    )
    assert "1" in error_text and "500" in error_text, (
        f"Error message must mention the allowed range [1, 500]. Got: {result['error']}"
    )


def test_ac6_hybridFusionWeight_error_mentions_field_and_range():
    script = """
import { resolveRetrievalConfig, parseConfigOverrides } from './src/config/retrieval.js';
const overrides = parseConfigOverrides({ hybridFusionWeight: '5.0' });
const { config, error } = resolveRetrievalConfig(null, overrides);
process.stdout.write(JSON.stringify({ error }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    result = json.loads(out)
    error_text = (result["error"] or "").lower()
    assert "hybridfusionweight" in error_text or "hybrid_fusion_weight" in error_text or "fusion" in error_text, (
        f"Error message must mention 'hybridFusionWeight'. Got: {result['error']}"
    )
    assert "0" in error_text and "1" in error_text, (
        f"Error message must mention the allowed range [0.0, 1.0]. Got: {result['error']}"
    )


def test_ac6_http_error_body_is_json_with_error_key():
    with _ServerProcess() as srv:
        status, headers, body = srv.get("/search?q=test&topK=0")
    assert status == 400
    data = json.loads(body)
    assert "error" in data, f"400 response must have 'error' key. Got: {data}"
    assert isinstance(data["error"], str) and len(data["error"]) > 0
