"""
TDD tests for issue #133: Add ablation runner for comparing retrieval presets.

AC1 — Running with ≥2 presets produces a formatted table showing Recall@k, nDCG, MRR,
       and average query latency per preset.
AC2 — Adding a new preset requires only a config change (YAML/JSON file); no code changes.
AC3 — Each preset can independently toggle hybrid search, reranker, and embedding model.
AC4 — Runner accepts --output flag to write JSON or CSV for longitudinal tracking.
AC5 — Output file includes timestamp and preset names alongside all metrics.
AC6 — Per-preset avg query latency (ms) in both printed table and output file.
AC7 — Runner works against the existing Thai eval set without additional data prep.
AC8 — Per-preset failure → report error per-preset and continue; do not abort.
"""

import csv
import json
import os
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVAL_DIR = os.path.join(REPO_ROOT, "src", "eval")
ABLATION_SCRIPT = os.path.join(EVAL_DIR, "run_ablation.py")
THAI_EVAL_SET = os.path.join(EVAL_DIR, "thai_eval_set.json")


# ---------------------------------------------------------------------------
# Mock search server helpers
# ---------------------------------------------------------------------------


class _MockSearchHandler(BaseHTTPRequestHandler):
    results_factory = None  # callable(query, k, params) -> list[dict] | Exception

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        query = qs.get("q", [""])[0]
        k = int(qs.get("k", ["10"])[0])
        factory = self.__class__.results_factory
        try:
            results = factory(query, k, qs) if factory else []
            payload = json.dumps({"results": results}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except Exception:
            self.send_response(500)
            self.end_headers()

    def log_message(self, *_):
        pass


def _start_mock_server(port, factory):
    _MockSearchHandler.results_factory = factory
    srv = HTTPServer(("localhost", port), _MockSearchHandler)
    t = threading.Thread(target=srv.serve_forever)
    t.daemon = True
    t.start()
    return srv


def _good_factory(query, k, params):
    return [{"id": "article-thai-001", "score": 0.9}]


def _run_ablation(args, extra_env=None):
    env = {**os.environ}
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, ABLATION_SCRIPT] + args,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )


def _write_json_config(presets, tmpdir=None):
    data = {"presets": presets}
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, dir=tmpdir, encoding="utf-8"
    )
    json.dump(data, f, ensure_ascii=False)
    f.close()
    return f.name


def _two_preset_config(port):
    return [
        {
            "name": "dense-only",
            "hybridEnabled": "false",
            "rerankEnabled": "false",
        },
        {
            "name": "hybrid",
            "hybridEnabled": "true",
            "rerankEnabled": "false",
        },
    ]


# ---------------------------------------------------------------------------
# Pre-flight: ablation script exists
# ---------------------------------------------------------------------------


def test_ablation_script_exists():
    assert os.path.isfile(ABLATION_SCRIPT), (
        f"src/eval/run_ablation.py must exist at {ABLATION_SCRIPT}"
    )


# ---------------------------------------------------------------------------
# AC1 — Formatted table with Recall@k, nDCG, MRR, latency for ≥2 presets
# ---------------------------------------------------------------------------


def test_ac1_table_shows_recall(tmp_path):
    port = 23101
    srv = _start_mock_server(port, _good_factory)
    cfg = _write_json_config(_two_preset_config(port), tmpdir=str(tmp_path))
    try:
        result = _run_ablation([
            "--config", cfg,
            "--search-url", f"http://localhost:{port}/search",
            "--k", "5",
        ])
        out = result.stdout + result.stderr
        assert "recall" in out.lower(), f"Table must show Recall metric:\n{out}"
    finally:
        srv.shutdown()
        os.unlink(cfg)


def test_ac1_table_shows_ndcg(tmp_path):
    port = 23102
    srv = _start_mock_server(port, _good_factory)
    cfg = _write_json_config(_two_preset_config(port), tmpdir=str(tmp_path))
    try:
        result = _run_ablation([
            "--config", cfg,
            "--search-url", f"http://localhost:{port}/search",
            "--k", "5",
        ])
        out = result.stdout + result.stderr
        assert "ndcg" in out.lower(), f"Table must show nDCG metric:\n{out}"
    finally:
        srv.shutdown()
        os.unlink(cfg)


def test_ac1_table_shows_mrr(tmp_path):
    port = 23103
    srv = _start_mock_server(port, _good_factory)
    cfg = _write_json_config(_two_preset_config(port), tmpdir=str(tmp_path))
    try:
        result = _run_ablation([
            "--config", cfg,
            "--search-url", f"http://localhost:{port}/search",
            "--k", "5",
        ])
        out = result.stdout + result.stderr
        assert "mrr" in out.lower(), f"Table must show MRR metric:\n{out}"
    finally:
        srv.shutdown()
        os.unlink(cfg)


def test_ac1_table_shows_latency(tmp_path):
    port = 23104
    srv = _start_mock_server(port, _good_factory)
    cfg = _write_json_config(_two_preset_config(port), tmpdir=str(tmp_path))
    try:
        result = _run_ablation([
            "--config", cfg,
            "--search-url", f"http://localhost:{port}/search",
            "--k", "5",
        ])
        out = result.stdout + result.stderr
        assert any(w in out.lower() for w in ("latency", "ms")), (
            f"Table must show latency metric:\n{out}"
        )
    finally:
        srv.shutdown()
        os.unlink(cfg)


def test_ac1_both_preset_names_in_output(tmp_path):
    port = 23105
    srv = _start_mock_server(port, _good_factory)
    cfg = _write_json_config(_two_preset_config(port), tmpdir=str(tmp_path))
    try:
        result = _run_ablation([
            "--config", cfg,
            "--search-url", f"http://localhost:{port}/search",
            "--k", "5",
        ])
        out = result.stdout + result.stderr
        assert "dense-only" in out, f"Preset name 'dense-only' must appear in output:\n{out}"
        assert "hybrid" in out, f"Preset name 'hybrid' must appear in output:\n{out}"
    finally:
        srv.shutdown()
        os.unlink(cfg)


def test_ac1_exit_zero_on_success(tmp_path):
    port = 23106
    srv = _start_mock_server(port, _good_factory)
    cfg = _write_json_config(_two_preset_config(port), tmpdir=str(tmp_path))
    try:
        result = _run_ablation([
            "--config", cfg,
            "--search-url", f"http://localhost:{port}/search",
            "--k", "5",
        ])
        assert result.returncode == 0, (
            f"Ablation runner must exit 0 on success:\n{result.stdout}\n{result.stderr}"
        )
    finally:
        srv.shutdown()
        os.unlink(cfg)


# ---------------------------------------------------------------------------
# AC2 — Adding a preset requires only config change, no code change
# ---------------------------------------------------------------------------


def test_ac2_third_preset_no_code_change(tmp_path):
    """Add a third preset to the config; runner must handle it without code change."""
    port = 23201
    srv = _start_mock_server(port, _good_factory)
    presets = _two_preset_config(port) + [
        {"name": "hybrid-rerank", "hybridEnabled": "true", "rerankEnabled": "true"}
    ]
    cfg = _write_json_config(presets, tmpdir=str(tmp_path))
    try:
        result = _run_ablation([
            "--config", cfg,
            "--search-url", f"http://localhost:{port}/search",
            "--k", "5",
        ])
        out = result.stdout + result.stderr
        assert "hybrid-rerank" in out, (
            f"Third preset 'hybrid-rerank' must appear in output without code change:\n{out}"
        )
        assert result.returncode == 0
    finally:
        srv.shutdown()
        os.unlink(cfg)


def test_ac2_yaml_config_accepted(tmp_path):
    """YAML config file is accepted (if pyyaml available) or falls back to JSON notation."""
    port = 23202
    srv = _start_mock_server(port, _good_factory)
    # Write a YAML config
    yaml_content = """presets:
  - name: dense-only
    hybridEnabled: "false"
    rerankEnabled: "false"
  - name: hybrid
    hybridEnabled: "true"
    rerankEnabled: "false"
"""
    cfg = tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, dir=str(tmp_path), encoding="utf-8"
    )
    cfg.write(yaml_content)
    cfg.close()
    try:
        result = _run_ablation([
            "--config", cfg.name,
            "--search-url", f"http://localhost:{port}/search",
            "--k", "5",
        ])
        out = result.stdout + result.stderr
        # Either succeeds (pyyaml available) or prints a clear error about YAML support
        if result.returncode == 0:
            assert "dense-only" in out
        else:
            assert "yaml" in out.lower() or "pyyaml" in out.lower() or "install" in out.lower(), (
                f"If YAML unsupported, must print clear message. Got:\n{out}"
            )
    finally:
        srv.shutdown()
        os.unlink(cfg.name)


# ---------------------------------------------------------------------------
# AC3 — Each preset independently toggles hybrid, reranker, embedding model
# ---------------------------------------------------------------------------


def test_ac3_preset_params_passed_to_search(tmp_path):
    """Verify that hybrid/rerank params from each preset reach the search endpoint."""
    port = 23301
    received_params = []

    def recording_factory(query, k, params):
        received_params.append({key: vals[0] for key, vals in params.items()})
        return [{"id": "article-thai-001", "score": 0.9}]

    srv = _start_mock_server(port, recording_factory)
    presets = [
        {"name": "no-hybrid", "hybridEnabled": "false", "rerankEnabled": "false"},
        {"name": "with-hybrid", "hybridEnabled": "true", "rerankEnabled": "false"},
    ]
    cfg = _write_json_config(presets, tmpdir=str(tmp_path))
    try:
        _run_ablation([
            "--config", cfg,
            "--search-url", f"http://localhost:{port}/search",
            "--k", "5",
        ])
        hybrid_vals = {p.get("hybridEnabled") for p in received_params}
        assert "false" in hybrid_vals or "False" in hybrid_vals, (
            "dense-only preset must send hybridEnabled=false"
        )
        assert "true" in hybrid_vals or "True" in hybrid_vals, (
            "hybrid preset must send hybridEnabled=true"
        )
    finally:
        srv.shutdown()
        os.unlink(cfg)


def test_ac3_embedding_model_can_be_set(tmp_path):
    """A preset can specify embeddingModelId and it is passed to the search URL."""
    port = 23302
    received = []

    def factory(query, k, params):
        received.append(dict(params))
        return [{"id": "article-thai-001", "score": 0.9}]

    srv = _start_mock_server(port, factory)
    presets = [
        {"name": "minilm", "hybridEnabled": "false", "embeddingModelId": "Xenova/all-MiniLM-L6-v2"},
        {"name": "e5", "hybridEnabled": "false", "embeddingModelId": "Xenova/multilingual-e5-small"},
    ]
    cfg = _write_json_config(presets, tmpdir=str(tmp_path))
    try:
        _run_ablation([
            "--config", cfg,
            "--search-url", f"http://localhost:{port}/search",
            "--k", "3",
        ])
        model_vals = set()
        for p in received:
            if "embeddingModelId" in p:
                model_vals.add(p["embeddingModelId"][0] if isinstance(p["embeddingModelId"], list) else p["embeddingModelId"])
        assert len(model_vals) >= 1, "embeddingModelId must be forwarded to search"
    finally:
        srv.shutdown()
        os.unlink(cfg)


# ---------------------------------------------------------------------------
# AC4 — --output flag writes JSON or CSV
# ---------------------------------------------------------------------------


def test_ac4_output_json_file_created(tmp_path):
    port = 23401
    srv = _start_mock_server(port, _good_factory)
    cfg = _write_json_config(_two_preset_config(port), tmpdir=str(tmp_path))
    out_file = str(tmp_path / "results.json")
    try:
        result = _run_ablation([
            "--config", cfg,
            "--search-url", f"http://localhost:{port}/search",
            "--k", "5",
            "--output", out_file,
        ])
        assert os.path.isfile(out_file), (
            f"--output results.json must create the file. Stdout:\n{result.stdout}\n{result.stderr}"
        )
    finally:
        srv.shutdown()
        os.unlink(cfg)


def test_ac4_output_json_is_valid_json(tmp_path):
    port = 23402
    srv = _start_mock_server(port, _good_factory)
    cfg = _write_json_config(_two_preset_config(port), tmpdir=str(tmp_path))
    out_file = str(tmp_path / "results.json")
    try:
        _run_ablation([
            "--config", cfg,
            "--search-url", f"http://localhost:{port}/search",
            "--k", "5",
            "--output", out_file,
        ])
        with open(out_file, encoding="utf-8") as f:
            data = json.load(f)
        assert isinstance(data, dict), "JSON output must be a dict"
    finally:
        srv.shutdown()
        os.unlink(cfg)


def test_ac4_output_csv_file_created(tmp_path):
    port = 23403
    srv = _start_mock_server(port, _good_factory)
    cfg = _write_json_config(_two_preset_config(port), tmpdir=str(tmp_path))
    out_file = str(tmp_path / "results.csv")
    try:
        result = _run_ablation([
            "--config", cfg,
            "--search-url", f"http://localhost:{port}/search",
            "--k", "5",
            "--output", out_file,
        ])
        assert os.path.isfile(out_file), (
            f"--output results.csv must create the file. Stdout:\n{result.stdout}\n{result.stderr}"
        )
    finally:
        srv.shutdown()
        os.unlink(cfg)


def test_ac4_output_csv_has_rows(tmp_path):
    port = 23404
    srv = _start_mock_server(port, _good_factory)
    cfg = _write_json_config(_two_preset_config(port), tmpdir=str(tmp_path))
    out_file = str(tmp_path / "results.csv")
    try:
        _run_ablation([
            "--config", cfg,
            "--search-url", f"http://localhost:{port}/search",
            "--k", "5",
            "--output", out_file,
        ])
        with open(out_file, encoding="utf-8") as f:
            rows = list(csv.reader(f))
        assert len(rows) >= 3, f"CSV must have header + ≥2 data rows, got {len(rows)} rows"
    finally:
        srv.shutdown()
        os.unlink(cfg)


# ---------------------------------------------------------------------------
# AC5 — Output file includes timestamp and preset names
# ---------------------------------------------------------------------------


def test_ac5_json_output_has_timestamp(tmp_path):
    port = 23501
    srv = _start_mock_server(port, _good_factory)
    cfg = _write_json_config(_two_preset_config(port), tmpdir=str(tmp_path))
    out_file = str(tmp_path / "results.json")
    try:
        _run_ablation([
            "--config", cfg,
            "--search-url", f"http://localhost:{port}/search",
            "--k", "5",
            "--output", out_file,
        ])
        with open(out_file, encoding="utf-8") as f:
            data = json.load(f)
        assert "timestamp" in data, f"JSON output must have 'timestamp' key. Got keys: {list(data.keys())}"
        assert data["timestamp"], "timestamp must be non-empty"
    finally:
        srv.shutdown()
        os.unlink(cfg)


def test_ac5_json_output_has_preset_names(tmp_path):
    port = 23502
    srv = _start_mock_server(port, _good_factory)
    cfg = _write_json_config(_two_preset_config(port), tmpdir=str(tmp_path))
    out_file = str(tmp_path / "results.json")
    try:
        _run_ablation([
            "--config", cfg,
            "--search-url", f"http://localhost:{port}/search",
            "--k", "5",
            "--output", out_file,
        ])
        with open(out_file, encoding="utf-8") as f:
            data = json.load(f)
        raw = json.dumps(data)
        assert "dense-only" in raw, "JSON output must include preset name 'dense-only'"
        assert "hybrid" in raw, "JSON output must include preset name 'hybrid'"
    finally:
        srv.shutdown()
        os.unlink(cfg)


def test_ac5_csv_has_timestamp_column(tmp_path):
    port = 23503
    srv = _start_mock_server(port, _good_factory)
    cfg = _write_json_config(_two_preset_config(port), tmpdir=str(tmp_path))
    out_file = str(tmp_path / "results.csv")
    try:
        _run_ablation([
            "--config", cfg,
            "--search-url", f"http://localhost:{port}/search",
            "--k", "5",
            "--output", out_file,
        ])
        with open(out_file, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            header = reader.fieldnames or []
        assert any("timestamp" in h.lower() for h in header), (
            f"CSV header must include timestamp column. Got: {header}"
        )
    finally:
        srv.shutdown()
        os.unlink(cfg)


def test_ac5_csv_has_preset_name_column(tmp_path):
    port = 23504
    srv = _start_mock_server(port, _good_factory)
    cfg = _write_json_config(_two_preset_config(port), tmpdir=str(tmp_path))
    out_file = str(tmp_path / "results.csv")
    try:
        _run_ablation([
            "--config", cfg,
            "--search-url", f"http://localhost:{port}/search",
            "--k", "5",
            "--output", out_file,
        ])
        with open(out_file, encoding="utf-8") as f:
            rows = list(csv.reader(f))
        assert len(rows) >= 2
        raw = "\n".join(",".join(r) for r in rows)
        assert "dense-only" in raw and "hybrid" in raw, (
            f"CSV must include preset names in data rows. Got:\n{raw}"
        )
    finally:
        srv.shutdown()
        os.unlink(cfg)


# ---------------------------------------------------------------------------
# AC6 — Per-preset avg latency in both table and output file
# ---------------------------------------------------------------------------


def test_ac6_latency_in_printed_table(tmp_path):
    port = 23601
    srv = _start_mock_server(port, _good_factory)
    cfg = _write_json_config(_two_preset_config(port), tmpdir=str(tmp_path))
    try:
        result = _run_ablation([
            "--config", cfg,
            "--search-url", f"http://localhost:{port}/search",
            "--k", "5",
        ])
        out = result.stdout + result.stderr
        import re
        numbers = re.findall(r"\d+\.\d+", out)
        assert numbers, f"Table must contain numeric latency values:\n{out}"
    finally:
        srv.shutdown()
        os.unlink(cfg)


def test_ac6_latency_in_json_output(tmp_path):
    port = 23602
    srv = _start_mock_server(port, _good_factory)
    cfg = _write_json_config(_two_preset_config(port), tmpdir=str(tmp_path))
    out_file = str(tmp_path / "results.json")
    try:
        _run_ablation([
            "--config", cfg,
            "--search-url", f"http://localhost:{port}/search",
            "--k", "5",
            "--output", out_file,
        ])
        with open(out_file, encoding="utf-8") as f:
            data = json.load(f)
        raw = json.dumps(data)
        assert "latency" in raw.lower(), f"JSON output must include latency field. Got: {raw[:500]}"
    finally:
        srv.shutdown()
        os.unlink(cfg)


def test_ac6_latency_in_csv_output(tmp_path):
    port = 23603
    srv = _start_mock_server(port, _good_factory)
    cfg = _write_json_config(_two_preset_config(port), tmpdir=str(tmp_path))
    out_file = str(tmp_path / "results.csv")
    try:
        _run_ablation([
            "--config", cfg,
            "--search-url", f"http://localhost:{port}/search",
            "--k", "5",
            "--output", out_file,
        ])
        with open(out_file, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            header = reader.fieldnames or []
        assert any("latency" in h.lower() or "ms" in h.lower() for h in header), (
            f"CSV must have a latency column. Got: {header}"
        )
    finally:
        srv.shutdown()
        os.unlink(cfg)


# ---------------------------------------------------------------------------
# AC7 — Works against existing Thai eval set
# ---------------------------------------------------------------------------


def test_ac7_thai_eval_set_exists():
    assert os.path.isfile(THAI_EVAL_SET), f"Thai eval set must exist at {THAI_EVAL_SET}"


def test_ac7_runner_uses_thai_eval_set_by_default(tmp_path):
    """Runner must work with the existing Thai eval set without extra prep."""
    port = 23701
    srv = _start_mock_server(port, _good_factory)
    cfg = _write_json_config(_two_preset_config(port), tmpdir=str(tmp_path))
    try:
        result = _run_ablation([
            "--config", cfg,
            "--search-url", f"http://localhost:{port}/search",
            "--k", "5",
        ])
        assert result.returncode == 0, (
            f"Runner must succeed with default Thai eval set:\n{result.stdout}\n{result.stderr}"
        )
    finally:
        srv.shutdown()
        os.unlink(cfg)


def test_ac7_custom_dataset_flag(tmp_path):
    """--dataset flag lets user specify an alternate eval set."""
    port = 23702
    srv = _start_mock_server(port, _good_factory)
    mini_dataset = [
        {"query": "การค้นหาเชิงความหมาย", "expected": ["article-thai-001"]},
        {"query": "เวกเตอร์ภาษาไทย", "expected": ["article-thai-001"]},
    ]
    ds_file = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, dir=str(tmp_path), encoding="utf-8"
    )
    json.dump(mini_dataset, ds_file, ensure_ascii=False)
    ds_file.close()
    cfg = _write_json_config(_two_preset_config(port), tmpdir=str(tmp_path))
    try:
        result = _run_ablation([
            "--config", cfg,
            "--search-url", f"http://localhost:{port}/search",
            "--k", "5",
            "--dataset", ds_file.name,
        ])
        assert result.returncode == 0, (
            f"Runner must accept --dataset flag:\n{result.stdout}\n{result.stderr}"
        )
    finally:
        srv.shutdown()
        os.unlink(cfg)
        os.unlink(ds_file.name)


# ---------------------------------------------------------------------------
# AC8 — Per-preset failure → report error and continue; do not abort
# ---------------------------------------------------------------------------


def test_ac8_bad_url_reports_error_continues(tmp_path):
    """Server returns 500 for one preset; runner must report error and continue."""
    port = 23801
    import socket as _socket

    class _SelectiveHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)
            qs = parse_qs(parsed.query)
            if qs.get("hybridEnabled", [""])[0] == "error_trigger":
                self.send_response(500)
                self.end_headers()
            else:
                results = [{"id": "article-thai-001", "score": 0.9}]
                payload = json.dumps({"results": results}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        def log_message(self, *_):
            pass

    srv = HTTPServer(("localhost", port), _SelectiveHandler)
    srv.socket.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEADDR, 1)
    t = threading.Thread(target=srv.serve_forever)
    t.daemon = True
    t.start()

    error_presets = [
        {"name": "good", "hybridEnabled": "false"},
        {"name": "bad", "hybridEnabled": "error_trigger"},
    ]
    cfg = _write_json_config(error_presets, tmpdir=str(tmp_path))
    try:
        result = _run_ablation([
            "--config", cfg,
            "--search-url", f"http://localhost:{port}/search",
            "--k", "3",
        ])
        out = result.stdout + result.stderr
        assert "bad" in out or "error" in out.lower() or "fail" in out.lower(), (
            f"Runner must report error for bad preset:\n{out}"
        )
        assert "good" in out, f"Runner must continue after error and show good preset:\n{out}"
    finally:
        srv.shutdown()
        os.unlink(cfg)


def test_ac8_missing_search_server_per_preset_continues(tmp_path):
    """If search server is unreachable, runner reports error per preset and continues."""
    presets = [
        {"name": "preset-a", "hybridEnabled": "false"},
        {"name": "preset-b", "hybridEnabled": "true"},
    ]
    cfg = _write_json_config(presets, tmpdir=str(tmp_path))
    try:
        result = _run_ablation([
            "--config", cfg,
            "--search-url", "http://localhost:1/search",  # nothing on port 1
            "--k", "3",
        ])
        out = result.stdout + result.stderr
        # Must not completely crash / stack trace; must print something about errors
        assert "preset-a" in out or "preset-b" in out or "error" in out.lower(), (
            f"Runner must mention presets or errors rather than silent crash:\n{out}"
        )
    finally:
        os.unlink(cfg)
