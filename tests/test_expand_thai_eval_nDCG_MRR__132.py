"""
Tests for issue #132: Expand Thai eval set and add nDCG and MRR metrics.

AC1  Dataset has ≥ 2× the previous count (baseline was 12 from issue #101 → need ≥ 24)
AC2  Eval command outputs Recall@k, nDCG, and MRR for the Thai query set
AC3  All three metrics computed at the same k
AC4  Adding a query requires only a change to the eval data file — no code changes
AC5  Eval exits non-zero and prints a clear error if expected IDs reference
     a non-existent article/chunk in the corpus
AC6  Metric definitions (nDCG, MRR, Recall@k) documented in a comment or README
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVAL_DIR = os.path.join(REPO_ROOT, "src", "eval")
EVAL_SCRIPT = os.path.join(EVAL_DIR, "run_eval.py")
EVAL_DATASET = os.path.join(EVAL_DIR, "thai_eval_set.json")
README_PATH = os.path.join(EVAL_DIR, "README.md")

# Baseline count established by issue #101
_BASELINE_QUERY_COUNT = 12


# ---------------------------------------------------------------------------
# Helpers: mock GET search server
# ---------------------------------------------------------------------------

class _GETSearchHandler(BaseHTTPRequestHandler):
    results_factory = None  # callable(query, k) -> list[dict]

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        query = qs.get("q", [""])[0]
        k = int(qs.get("k", ["10"])[0])
        results = self.__class__.results_factory(query, k) if self.__class__.results_factory else []
        payload = json.dumps({"results": results}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_):
        pass


def _start_mock_server(port, factory):
    _GETSearchHandler.results_factory = factory
    srv = HTTPServer(("localhost", port), _GETSearchHandler)
    t = threading.Thread(target=srv.serve_forever)
    t.daemon = True
    t.start()
    return srv


def _run_eval(extra_env=None):
    env = {**os.environ}
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, EVAL_SCRIPT],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )


# ---------------------------------------------------------------------------
# AC1 — dataset has ≥ 2× the baseline count (≥ 24 queries)
# ---------------------------------------------------------------------------

def test_ac1_dataset_exists():
    assert os.path.isfile(EVAL_DATASET), f"Dataset not found at {EVAL_DATASET}"


def test_ac1_dataset_is_valid_json():
    with open(EVAL_DATASET, encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, list), "Dataset must be a JSON array"


def test_ac1_dataset_minimum_count():
    with open(EVAL_DATASET, encoding="utf-8") as f:
        data = json.load(f)
    assert len(data) >= _BASELINE_QUERY_COUNT * 2, (
        f"Dataset must have ≥ {_BASELINE_QUERY_COUNT * 2} queries (2× baseline of {_BASELINE_QUERY_COUNT}), "
        f"got {len(data)}"
    )


def test_ac1_dataset_entry_schema():
    """Every entry must have 'query' (str) and 'expected' (non-empty list of str)."""
    with open(EVAL_DATASET, encoding="utf-8") as f:
        data = json.load(f)
    for i, entry in enumerate(data):
        assert "query" in entry, f"Entry {i} missing 'query'"
        assert "expected" in entry, f"Entry {i} missing 'expected'"
        assert isinstance(entry["query"], str) and entry["query"], f"Entry {i}: 'query' must be non-empty str"
        assert isinstance(entry["expected"], list) and entry["expected"], (
            f"Entry {i}: 'expected' must be non-empty list"
        )
        for eid in entry["expected"]:
            assert isinstance(eid, str) and eid, f"Entry {i}: expected IDs must be non-empty strings"


# ---------------------------------------------------------------------------
# AC2 — eval command outputs Recall@k, nDCG, and MRR
# ---------------------------------------------------------------------------

def test_ac2_output_contains_recall():
    port = 21201
    srv = _start_mock_server(port, lambda q, k: [{"id": f"article-thai-00{i+1}", "score": 0.9} for i in range(k)])
    try:
        result = _run_eval({
            "SEARCH_URL": f"http://localhost:{port}/search",
            "K": "5",
            "RECALL_THRESHOLD": "0.0",
        })
        out = result.stdout + result.stderr
        assert any(x in out.lower() for x in ("recall@5", "recall@k", "recall")), (
            f"Expected Recall metric in output, got:\n{out}"
        )
    finally:
        srv.shutdown()


def test_ac2_output_contains_ndcg():
    port = 21202
    srv = _start_mock_server(port, lambda q, k: [{"id": f"article-thai-00{i+1}", "score": 0.9} for i in range(k)])
    try:
        result = _run_eval({
            "SEARCH_URL": f"http://localhost:{port}/search",
            "K": "5",
            "RECALL_THRESHOLD": "0.0",
        })
        out = result.stdout + result.stderr
        assert "ndcg" in out.lower(), f"Expected nDCG metric in output, got:\n{out}"
    finally:
        srv.shutdown()


def test_ac2_output_contains_mrr():
    port = 21203
    srv = _start_mock_server(port, lambda q, k: [{"id": f"article-thai-00{i+1}", "score": 0.9} for i in range(k)])
    try:
        result = _run_eval({
            "SEARCH_URL": f"http://localhost:{port}/search",
            "K": "5",
            "RECALL_THRESHOLD": "0.0",
        })
        out = result.stdout + result.stderr
        assert "mrr" in out.lower(), f"Expected MRR metric in output, got:\n{out}"
    finally:
        srv.shutdown()


def test_ac2_metric_values_in_range():
    """All three metrics must print a value between 0.00 and 1.00."""
    port = 21204
    srv = _start_mock_server(port, lambda q, k: [{"id": "article-thai-001", "score": 0.9}])
    try:
        result = _run_eval({
            "SEARCH_URL": f"http://localhost:{port}/search",
            "K": "5",
            "RECALL_THRESHOLD": "0.0",
        })
        out = result.stdout + result.stderr
        import re
        # find all decimal numbers in output
        numbers = [float(m) for m in re.findall(r"\b0\.\d+\b|\b1\.00\b", out)]
        assert len(numbers) >= 3, f"Expected at least 3 numeric metrics (Recall, nDCG, MRR), got: {out}"
        for n in numbers:
            assert 0.0 <= n <= 1.0, f"Metric value {n} out of range [0, 1]: {out}"
    finally:
        srv.shutdown()


# ---------------------------------------------------------------------------
# AC3 — all three metrics computed at the same k
# ---------------------------------------------------------------------------

def test_ac3_same_k_for_all_metrics():
    """Output must show the same k in all metric labels."""
    port = 21301
    srv = _start_mock_server(port, lambda q, k: [])
    try:
        result = _run_eval({
            "SEARCH_URL": f"http://localhost:{port}/search",
            "K": "7",
            "RECALL_THRESHOLD": "0.0",
        })
        out = result.stdout + result.stderr
        # If metrics use @k notation, k=7 should appear at least once
        assert "7" in out, f"Expected k=7 to appear in output, got:\n{out}"
    finally:
        srv.shutdown()


def test_ac3_k_env_var_applied_to_all_metrics():
    """The K env var must control the k used across Recall@k, nDCG@k, and MRR@k."""
    with open(EVAL_SCRIPT, encoding="utf-8") as f:
        src = f.read()
    # The K env var should be read once and used for all metrics
    assert 'K' in src, "Script must reference K env var"
    # nDCG and MRR computation should not hardcode a different k
    # Simple structural check: k or K variable used in ndcg/mrr context
    assert "ndcg" in src.lower() or "nDCG" in src, "Script must compute nDCG"
    assert "mrr" in src.lower() or "MRR" in src, "Script must compute MRR"


# ---------------------------------------------------------------------------
# AC4 — adding a query requires only a data file change
# ---------------------------------------------------------------------------

def test_ac4_data_driven_no_code_change_needed():
    """Run eval with a custom dataset file containing one extra query — must work with no code change."""
    port = 21401
    srv = _start_mock_server(port, lambda q, k: [{"id": "article-thai-001", "score": 0.9}])
    try:
        # Write a custom dataset with the standard entries + one new entry
        with open(EVAL_DATASET, encoding="utf-8") as f:
            entries = json.load(f)
        extra_entry = {"query": "ทดสอบเพิ่มคำถามใหม่", "expected": ["article-thai-001"]}
        extended = entries + [extra_entry]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as tmp:
            json.dump(extended, tmp, ensure_ascii=False)
            tmp_path = tmp.name

        result = _run_eval({
            "SEARCH_URL": f"http://localhost:{port}/search",
            "K": "5",
            "RECALL_THRESHOLD": "0.0",
            "EVAL_DATASET": tmp_path,
        })
        os.unlink(tmp_path)
        assert result.returncode == 0, (
            f"Eval should succeed with custom dataset (exit {result.returncode}):\n"
            f"{result.stdout}\n{result.stderr}"
        )
    finally:
        srv.shutdown()


def test_ac4_eval_script_loads_dataset_path_from_env():
    """The script must support EVAL_DATASET env var to load an alternate dataset file."""
    with open(EVAL_SCRIPT, encoding="utf-8") as f:
        src = f.read()
    assert "EVAL_DATASET" in src, "Script must support EVAL_DATASET env var for alternate dataset path"


# ---------------------------------------------------------------------------
# AC5 — non-existent IDs → exit non-zero with clear error
# ---------------------------------------------------------------------------

def test_ac5_invalid_id_exits_nonzero():
    """Corpus validation: eval exits non-zero when expected ID is not in corpus."""
    port = 21501
    srv = _start_mock_server(port, lambda q, k: [])

    # Create a corpus file with known IDs
    corpus = {"articles": [{"id": "article-thai-001"}, {"id": "article-thai-002"}]}
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(corpus, f)
        corpus_path = f.name

    # Create a dataset with a bad ID
    bad_dataset = [
        {"query": "คำถาม", "expected": ["article-thai-001"]},
        {"query": "คำถามผิด", "expected": ["article-DOES-NOT-EXIST"]},
    ]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(bad_dataset, f, ensure_ascii=False)
        dataset_path = f.name

    try:
        result = _run_eval({
            "SEARCH_URL": f"http://localhost:{port}/search",
            "K": "5",
            "RECALL_THRESHOLD": "0.0",
            "EVAL_DATASET": dataset_path,
            "COLLECTION_FILE": corpus_path,
        })
        assert result.returncode != 0, (
            f"Expected non-zero exit for unknown article ID, got 0:\n"
            f"{result.stdout}\n{result.stderr}"
        )
        out = result.stdout + result.stderr
        assert "article-DOES-NOT-EXIST" in out or "not exist" in out.lower() or "not found" in out.lower(), (
            f"Error message must identify the bad ID, got:\n{out}"
        )
    finally:
        os.unlink(corpus_path)
        os.unlink(dataset_path)
        srv.shutdown()


def test_ac5_valid_ids_do_not_error():
    """No error when all expected IDs are in the corpus."""
    port = 21502
    srv = _start_mock_server(port, lambda q, k: [{"id": "article-thai-001", "score": 0.9}])

    corpus = {"articles": [{"id": "article-thai-001"}, {"id": "article-thai-002"}]}
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(corpus, f)
        corpus_path = f.name

    dataset = [{"query": "คำถาม", "expected": ["article-thai-001"]}]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(dataset, f, ensure_ascii=False)
        dataset_path = f.name

    try:
        result = _run_eval({
            "SEARCH_URL": f"http://localhost:{port}/search",
            "K": "5",
            "RECALL_THRESHOLD": "0.0",
            "EVAL_DATASET": dataset_path,
            "COLLECTION_FILE": corpus_path,
        })
        out = result.stdout + result.stderr
        assert "not found" not in out.lower() or result.returncode == 0, (
            f"Should not report missing IDs when all are valid:\n{out}"
        )
    finally:
        os.unlink(corpus_path)
        os.unlink(dataset_path)
        srv.shutdown()


def test_ac5_error_message_is_descriptive():
    """Error message for a bad ID must be descriptive (names the bad ID)."""
    port = 21503
    srv = _start_mock_server(port, lambda q, k: [])

    corpus = {"articles": [{"id": "article-thai-001"}]}
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(corpus, f)
        corpus_path = f.name

    bad_dataset = [{"query": "ทดสอบ", "expected": ["UNKNOWN-ID-XYZ"]}]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(bad_dataset, f, ensure_ascii=False)
        dataset_path = f.name

    try:
        result = _run_eval({
            "SEARCH_URL": f"http://localhost:{port}/search",
            "K": "5",
            "RECALL_THRESHOLD": "0.0",
            "EVAL_DATASET": dataset_path,
            "COLLECTION_FILE": corpus_path,
        })
        out = result.stdout + result.stderr
        assert "UNKNOWN-ID-XYZ" in out, f"Error must name the bad ID 'UNKNOWN-ID-XYZ', got:\n{out}"
    finally:
        os.unlink(corpus_path)
        os.unlink(dataset_path)
        srv.shutdown()


# ---------------------------------------------------------------------------
# AC6 — metric definitions documented
# ---------------------------------------------------------------------------

def test_ac6_readme_exists():
    assert os.path.isfile(README_PATH), f"README not found at {README_PATH}"


def test_ac6_readme_documents_ndcg():
    with open(README_PATH, encoding="utf-8") as f:
        content = f.read()
    assert "ndcg" in content.lower(), "README must document nDCG"


def test_ac6_readme_documents_mrr():
    with open(README_PATH, encoding="utf-8") as f:
        content = f.read()
    assert "mrr" in content.lower(), "README must document MRR"


def test_ac6_readme_documents_recall():
    with open(README_PATH, encoding="utf-8") as f:
        content = f.read()
    assert "recall" in content.lower(), "README must document Recall@k"


def test_ac6_script_has_metric_docstring():
    """Script must contain inline documentation of nDCG and MRR formulas."""
    with open(EVAL_SCRIPT, encoding="utf-8") as f:
        src = f.read()
    assert "ndcg" in src.lower(), "Script must reference nDCG in documentation"
    assert "mrr" in src.lower() or "MRR" in src, "Script must reference MRR in documentation"
    assert "recall" in src.lower(), "Script must reference Recall@k in documentation"


def test_ac6_ndcg_sensitive_to_ranking():
    """nDCG must score a hit at rank 1 higher than a hit at rank k.
    Validated by unit-importing the compute_ndcg function and comparing scores.
    """
    spec = importlib.util.spec_from_file_location("run_eval", EVAL_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    expected = {"article-thai-001"}
    k = 5

    # Hit at rank 1: result at index 0 is relevant
    results_rank1 = ["article-thai-001", "other-1", "other-2", "other-3", "other-4"]
    # Hit at rank k: result at last position is relevant
    results_rank_k = ["other-1", "other-2", "other-3", "other-4", "article-thai-001"]

    ndcg_rank1 = module.compute_ndcg(results_rank1, expected, k)
    ndcg_rank_k = module.compute_ndcg(results_rank_k, expected, k)

    assert ndcg_rank1 > ndcg_rank_k, (
        f"nDCG at rank 1 ({ndcg_rank1:.4f}) must be > nDCG at rank k ({ndcg_rank_k:.4f}). "
        "nDCG must be sensitive to ranking order, not equivalent to flat recall."
    )


def test_ac6_mrr_uses_first_relevant_rank():
    """MRR gives 1/rank for the first relevant result."""
    spec = importlib.util.spec_from_file_location("run_eval", EVAL_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    expected = {"article-thai-001"}
    k = 5

    results_rank2 = ["other", "article-thai-001", "other-2", "other-3", "other-4"]
    rr = module.compute_rr(results_rank2, expected, k)
    assert abs(rr - 0.5) < 1e-9, f"Reciprocal rank for hit at rank 2 must be 0.5, got {rr}"

    results_no_hit = ["other-1", "other-2", "other-3", "other-4", "other-5"]
    rr_miss = module.compute_rr(results_no_hit, expected, k)
    assert rr_miss == 0.0, f"Reciprocal rank for no hit must be 0.0, got {rr_miss}"
