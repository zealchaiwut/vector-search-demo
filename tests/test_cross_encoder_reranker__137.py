"""
TDD tests for issue #137: Add cross-encoder reranker behind Reranker interface.

AC1 — A Reranker interface exists in src/rerank/ and is the sole public contract consumers depend on
AC2 — The interface exposes a method that accepts a query string and an ordered list of chunk strings
       and returns a numeric relevance score per chunk
AC3 — A concrete BgeRerankerV2M3 implementation satisfies the Reranker interface
AC4 — The implementation tries Transformers.js ONNX first; if unavailable falls back to sidecar
       without requiring code changes by the caller
AC5 — The Reranker implementation is resolved through the interface (factory in src/rerank/)
AC6 — Thai-language query + Thai-language chunks: most relevant chunk scores higher than unrelated chunk
AC7 — No reranker logic leaks outside src/rerank/; embedder and store modules are not modified
AC8 — Tests cover: correct score ordering for English pair, Thai pair, graceful fallback when ONNX absent
"""

import json
import os
import subprocess


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RERANK_DIR = os.path.join(REPO_ROOT, "src", "rerank")
RERANK_INDEX_JS = os.path.join(RERANK_DIR, "index.js")
RERANK_IMPL_JS = os.path.join(RERANK_DIR, "BgeRerankerV2M3.js")
RERANK_SIDECAR_JS = os.path.join(RERANK_DIR, "sidecar.js")

# Force sidecar path in tests to avoid downloading ONNX model (~200 MB) in CI.
# The sidecar uses character n-gram overlap scoring which is deterministic and correct.
FORCE_SIDECAR_ENV = {"RERANKER_MODEL_ID": "invalid-nonexistent-model-for-testing-xyz"}


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


# ---------------------------------------------------------------------------
# AC1 — Reranker module exists in src/rerank/
# ---------------------------------------------------------------------------

def test_ac1_rerank_index_exists():
    assert os.path.isfile(RERANK_INDEX_JS), "src/rerank/index.js must exist"


def test_ac1_rerank_index_exports_create_reranker():
    with open(RERANK_INDEX_JS) as fh:
        src = fh.read()
    assert "createReranker" in src, "src/rerank/index.js must export createReranker"


def test_ac1_rerank_is_sole_public_contract():
    """The search module must import the reranker from src/rerank/, not implement it inline."""
    search_path = os.path.join(REPO_ROOT, "src", "search", "index.js")
    with open(search_path) as fh:
        src = fh.read()
    assert "../rerank" in src or "src/rerank" in src, (
        "src/search/index.js must delegate to src/rerank/ (not inline reranker logic)"
    )


# ---------------------------------------------------------------------------
# AC2 — Interface: rerank(query, chunks) → number[]
# ---------------------------------------------------------------------------

def test_ac2_create_reranker_returns_object_with_rerank_method():
    script = """
import { createReranker } from './src/rerank/index.js';
const r = createReranker();
process.stdout.write(JSON.stringify({ hasRerank: typeof r.rerank === 'function' }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["hasRerank"] is True


def test_ac2_rerank_returns_array_of_numbers():
    script = """
import { createReranker } from './src/rerank/index.js';
const r = createReranker();
const scores = await r.rerank(
  'What is the capital of France?',
  ['Paris is the capital of France', 'The Eiffel Tower was built in 1889']
);
const ok = Array.isArray(scores) && scores.length === 2 && scores.every(s => typeof s === 'number');
process.stdout.write(JSON.stringify({ scores, ok }));
"""
    out, err, rc = _run_node(script, env=FORCE_SIDECAR_ENV)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["ok"] is True, f"rerank() must return number[]; got: {data.get('scores')}"


def test_ac2_rerank_returns_one_score_per_chunk():
    script = """
import { createReranker } from './src/rerank/index.js';
const r = createReranker();
const chunks = ['chunk one', 'chunk two', 'chunk three'];
const scores = await r.rerank('query', chunks);
process.stdout.write(JSON.stringify({ len: scores.length, expected: chunks.length }));
"""
    out, err, rc = _run_node(script, env=FORCE_SIDECAR_ENV)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["len"] == data["expected"], "Must return exactly one score per input chunk"


def test_ac2_rerank_empty_chunks_returns_empty_array():
    script = """
import { createReranker } from './src/rerank/index.js';
const r = createReranker();
const scores = await r.rerank('query', []);
process.stdout.write(JSON.stringify({ scores }));
"""
    out, err, rc = _run_node(script, env=FORCE_SIDECAR_ENV)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["scores"] == [], "Empty chunk list must return empty array"


# ---------------------------------------------------------------------------
# AC3 — BgeRerankerV2M3 concrete implementation
# ---------------------------------------------------------------------------

def test_ac3_bge_reranker_impl_file_exists():
    assert os.path.isfile(RERANK_IMPL_JS), "src/rerank/BgeRerankerV2M3.js must exist"


def test_ac3_bge_reranker_has_rerank_method():
    script = """
import { BgeRerankerV2M3 } from './src/rerank/BgeRerankerV2M3.js';
const r = new BgeRerankerV2M3();
process.stdout.write(JSON.stringify({ hasRerank: typeof r.rerank === 'function' }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["hasRerank"] is True


def test_ac3_bge_reranker_is_exported_from_index():
    with open(RERANK_INDEX_JS) as fh:
        src = fh.read()
    assert "BgeRerankerV2M3" in src, "src/rerank/index.js must export BgeRerankerV2M3"


# ---------------------------------------------------------------------------
# AC4 — Graceful fallback when ONNX / Transformers.js model unavailable
# ---------------------------------------------------------------------------

def test_ac4_sidecar_script_exists():
    assert os.path.isfile(RERANK_SIDECAR_JS), "src/rerank/sidecar.js must exist"


def test_ac4_sidecar_reads_stdin_writes_stdout():
    """Sidecar reads {query, chunks} from stdin and writes {scores} to stdout."""
    input_data = json.dumps({
        "query": "What is the capital of France?",
        "chunks": ["Paris is the capital of France", "The Eiffel Tower was built in 1889"],
    })
    result = subprocess.run(
        ["node", RERANK_SIDECAR_JS],
        input=input_data,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=30,
    )
    assert result.returncode == 0, f"Sidecar error: {result.stderr}"
    data = json.loads(result.stdout)
    assert "scores" in data, "Sidecar must output {scores: number[]}"
    assert len(data["scores"]) == 2
    assert all(isinstance(s, (int, float)) for s in data["scores"])


def test_ac4_graceful_fallback_returns_scores_when_onnx_absent():
    """When the ONNX model cannot be loaded, the reranker falls back to sidecar and returns scores."""
    script = """
import { createReranker } from './src/rerank/index.js';
const r = createReranker();
const scores = await r.rerank(
  'What is the capital of France?',
  ['Paris is the capital of France', 'The Eiffel Tower was built in 1889']
);
process.stdout.write(JSON.stringify({ scores, ok: Array.isArray(scores) && scores.length === 2 }));
"""
    out, err, rc = _run_node(script, env=FORCE_SIDECAR_ENV)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["ok"] is True, f"Must return scores even when ONNX model unavailable: {data}"


def test_ac4_fallback_correct_ordering_english():
    """Sidecar fallback must produce correct score ordering for English pair."""
    script = """
import { createReranker } from './src/rerank/index.js';
const r = createReranker();
const scores = await r.rerank(
  'What is the capital of France?',
  ['Paris is the capital of France', 'The Eiffel Tower was built in 1889']
);
process.stdout.write(JSON.stringify({ scores, ok: scores[0] > scores[1] }));
"""
    out, err, rc = _run_node(script, env=FORCE_SIDECAR_ENV)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["ok"] is True, (
        f"Capital-of-France chunk must score higher than Eiffel-Tower chunk: {data['scores']}"
    )


# ---------------------------------------------------------------------------
# AC5 — Factory resolution point in src/rerank/
# ---------------------------------------------------------------------------

def test_ac5_create_reranker_returns_bge_instance():
    script = """
import { createReranker } from './src/rerank/index.js';
import { BgeRerankerV2M3 } from './src/rerank/BgeRerankerV2M3.js';
const r = createReranker();
process.stdout.write(JSON.stringify({ isBge: r instanceof BgeRerankerV2M3 }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["isBge"] is True, "createReranker() must return a BgeRerankerV2M3 instance"


def test_ac5_swapping_impl_requires_only_index_change():
    """No files outside src/rerank/ should import BgeRerankerV2M3 directly."""
    outside_rerank = []
    src_root = os.path.join(REPO_ROOT, "src")
    for dirpath, dirnames, filenames in os.walk(src_root):
        dirnames[:] = [d for d in dirnames if d != "rerank"]
        for fname in filenames:
            if not fname.endswith(".js"):
                continue
            fpath = os.path.join(dirpath, fname)
            with open(fpath) as fh:
                content = fh.read()
            if "BgeRerankerV2M3" in content:
                outside_rerank.append(fpath)
    assert outside_rerank == [], (
        f"BgeRerankerV2M3 must only be referenced inside src/rerank/: {outside_rerank}"
    )


# ---------------------------------------------------------------------------
# AC6 — Score ordering: Thai pair
# ---------------------------------------------------------------------------

def test_ac6_thai_pair_correct_ordering():
    """Thai direct-answer chunk must score higher than tangentially related chunk."""
    script = """
import { createReranker } from './src/rerank/index.js';
const r = createReranker();
const scores = await r.rerank(
  'เมืองหลวงของประเทศไทยคืออะไร',
  [
    'กรุงเทพมหานครเป็นเมืองหลวงของประเทศไทย',
    'วัดพระแก้วตั้งอยู่ในกรุงเทพมหานคร'
  ]
);
process.stdout.write(JSON.stringify({ scores, ok: scores[0] > scores[1] }));
"""
    out, err, rc = _run_node(script, env=FORCE_SIDECAR_ENV)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["ok"] is True, (
        f"Thai capital chunk must score higher than temple chunk: {data['scores']}"
    )


def test_ac6_thai_scores_are_non_negative():
    """All scores for Thai chunks must be non-negative numbers."""
    script = """
import { createReranker } from './src/rerank/index.js';
const r = createReranker();
const scores = await r.rerank(
  'เมืองหลวงของประเทศไทยคืออะไร',
  [
    'กรุงเทพมหานครเป็นเมืองหลวงของประเทศไทย',
    'วัดพระแก้วตั้งอยู่ในกรุงเทพมหานคร'
  ]
);
const ok = scores.every(s => typeof s === 'number' && s >= 0);
process.stdout.write(JSON.stringify({ scores, ok }));
"""
    out, err, rc = _run_node(script, env=FORCE_SIDECAR_ENV)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["ok"] is True, f"Scores must be non-negative: {data['scores']}"


# ---------------------------------------------------------------------------
# AC7 — No reranker logic in embedder or store modules
# ---------------------------------------------------------------------------

def test_ac7_embedder_not_modified():
    embedder_path = os.path.join(REPO_ROOT, "src", "embeddings", "index.js")
    with open(embedder_path) as fh:
        src = fh.read()
    assert "rerank" not in src.lower(), "Embedder module must not contain reranker logic"


def test_ac7_store_index_not_modified():
    store_path = os.path.join(REPO_ROOT, "src", "store", "index.js")
    with open(store_path) as fh:
        src = fh.read()
    assert "rerank" not in src.lower(), "Store index must not contain reranker logic"


def test_ac7_mock_store_not_modified():
    path = os.path.join(REPO_ROOT, "src", "store", "MockStore.js")
    with open(path) as fh:
        src = fh.read()
    assert "rerank" not in src.lower(), "MockStore must not contain reranker logic"


# ---------------------------------------------------------------------------
# AC8 — Integration: search pipeline delegates to reranker when enabled
# ---------------------------------------------------------------------------

def test_ac8_search_with_rerank_enabled_does_not_error():
    """searchDocuments with rerankEnabled=true must complete without error."""
    script = """
import { searchDocuments } from './src/search/index.js';
const cfg = {
  embeddingModelId: 'Xenova/multilingual-e5-small',
  topK: 5,
  hybridEnabled: false,
  rrfK: 60,
  hybridFusionWeight: 0.7,
  rerankEnabled: true,
  rerankModelId: 'cross-encoder/ms-marco-MiniLM-L-6-v2',
  chunkSize: 400,
  chunkOverlap: 80,
  textNormalisationEnabled: true,
};
const results = await searchDocuments('test query', 5, null, cfg, false);
process.stdout.write(JSON.stringify({ ok: Array.isArray(results) }));
"""
    out, err, rc = _run_node(script, env=FORCE_SIDECAR_ENV)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["ok"] is True, "searchDocuments with rerankEnabled must return an array"


def test_ac8_reranker_called_from_search_pipeline():
    """With rerankEnabled=true, the search pipeline must call into src/rerank/."""
    search_path = os.path.join(REPO_ROOT, "src", "search", "index.js")
    with open(search_path) as fh:
        src = fh.read()
    # The search pipeline must reference the rerank module (not implement scoring inline)
    assert "../rerank" in src, (
        "src/search/index.js must import from ../rerank/ when rerankEnabled is true"
    )
