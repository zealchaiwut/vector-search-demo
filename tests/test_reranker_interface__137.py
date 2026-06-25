"""Tests for issue #137: Add cross-encoder reranker behind Reranker interface

Acceptance Criteria:
AC1: A Reranker interface exists in src/rerank/ and is the sole public contract
AC2: The interface exposes a method accepting query string + chunk list, returns scores
AC3: A concrete BgeRerankerV2M3 implementation satisfies the Reranker interface
AC4: Implementation tries Transformers.js ONNX first; falls back to sidecar without caller changes
AC5: Reranker resolved through factory in src/rerank/ (swapping requires no changes outside src/rerank/)
AC6: Thai query + Thai chunks: most relevant chunk scores higher than unrelated chunk
AC7: No reranker logic leaks outside src/rerank/; embedder and store modules not modified
AC8: Tests cover: English pair score ordering, Thai pair ordering, graceful fallback

This test runs against a potentially-running Node.js environment using subprocess.
"""

import json
import os
import subprocess


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RERANK_DIR = os.path.join(REPO_ROOT, "src", "rerank")
RERANK_INDEX_JS = os.path.join(RERANK_DIR, "index.js")
RERANK_IMPL_JS = os.path.join(RERANK_DIR, "BgeRerankerV2M3.js")
RERANK_SIDECAR_JS = os.path.join(RERANK_DIR, "sidecar.js")

# Force sidecar to avoid downloading ONNX model (~200 MB) in tests
FORCE_SIDECAR_ENV = {"RERANKER_MODEL_ID": "invalid-nonexistent-model-for-testing-xyz"}


def _run_node(script, env=None, timeout=60):
    """Run a Node.js ESM script and return (stdout, stderr, returncode)."""
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


# --- AC1: Reranker interface in src/rerank/ ---

def test_ac1_rerank_index_exists():
    """AC1: src/rerank/index.js must exist"""
    assert os.path.isfile(RERANK_INDEX_JS), f"src/rerank/index.js must exist at {RERANK_INDEX_JS}"


def test_ac1_create_reranker_exported():
    """AC1: createReranker must be exported from src/rerank/index.js"""
    with open(RERANK_INDEX_JS) as fh:
        src = fh.read()
    assert "createReranker" in src, "src/rerank/index.js must export createReranker"


def test_ac1_sole_public_contract():
    """AC1: Search module must import from src/rerank/, not implement inline"""
    search_path = os.path.join(REPO_ROOT, "src", "search", "index.js")
    with open(search_path) as fh:
        src = fh.read()
    assert "../rerank" in src or "src/rerank" in src, (
        "src/search/index.js must delegate to src/rerank/ (sole public contract)"
    )


# --- AC2: Interface contract: rerank(query, chunks) → number[] ---

def test_ac2_rerank_method_exists():
    """AC2: Reranker instance has rerank() method"""
    script = """
import { createReranker } from './src/rerank/index.js';
const r = createReranker();
process.stdout.write(JSON.stringify({ hasRerank: typeof r.rerank === 'function' }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node invocation failed: {err}"
    data = json.loads(out)
    assert data["hasRerank"], "Reranker instance must have rerank() method"


def test_ac2_rerank_returns_number_array():
    """AC2: rerank(query, chunks) returns array of numbers"""
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
    assert data["ok"], f"rerank() must return number[]; got: {data.get('scores')}"


def test_ac2_one_score_per_chunk():
    """AC2: Returns exactly one score per input chunk"""
    script = """
import { createReranker } from './src/rerank/index.js';
const r = createReranker();
const chunks = ['chunk one', 'chunk two', 'chunk three'];
const scores = await r.rerank('sample query', chunks);
process.stdout.write(JSON.stringify({ len: scores.length, expected: chunks.length }));
"""
    out, err, rc = _run_node(script, env=FORCE_SIDECAR_ENV)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["len"] == data["expected"], "Must return exactly one score per input chunk"


def test_ac2_empty_chunks_returns_empty_array():
    """AC2: Empty chunk list returns empty array (edge case)"""
    script = """
import { createReranker } from './src/rerank/index.js';
const r = createReranker();
const scores = await r.rerank('query', []);
process.stdout.write(JSON.stringify({ scores, isEmpty: scores.length === 0 }));
"""
    out, err, rc = _run_node(script, env=FORCE_SIDECAR_ENV)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["isEmpty"], f"Empty chunks must return empty array; got: {data['scores']}"


# --- AC3: BgeRerankerV2M3 concrete implementation ---

def test_ac3_bge_impl_file_exists():
    """AC3: BgeRerankerV2M3 implementation file exists"""
    assert os.path.isfile(RERANK_IMPL_JS), f"src/rerank/BgeRerankerV2M3.js must exist at {RERANK_IMPL_JS}"


def test_ac3_bge_instantiable():
    """AC3: BgeRerankerV2M3 can be instantiated"""
    script = """
import { BgeRerankerV2M3 } from './src/rerank/BgeRerankerV2M3.js';
const r = new BgeRerankerV2M3();
process.stdout.write(JSON.stringify({ hasRerank: typeof r.rerank === 'function' }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["hasRerank"], "BgeRerankerV2M3 must have rerank() method"


def test_ac3_bge_exported_from_index():
    """AC3: BgeRerankerV2M3 is exported from src/rerank/index.js"""
    with open(RERANK_INDEX_JS) as fh:
        src = fh.read()
    assert "BgeRerankerV2M3" in src, "src/rerank/index.js must export BgeRerankerV2M3"


# --- AC4: Graceful fallback when ONNX unavailable ---

def test_ac4_sidecar_exists():
    """AC4: Sidecar script exists at src/rerank/sidecar.js"""
    assert os.path.isfile(RERANK_SIDECAR_JS), f"src/rerank/sidecar.js must exist at {RERANK_SIDECAR_JS}"


def test_ac4_sidecar_io_contract():
    """AC4: Sidecar reads {query, chunks} from stdin, writes {scores} to stdout"""
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
    assert result.returncode == 0, f"Sidecar failed: {result.stderr}"
    data = json.loads(result.stdout)
    assert "scores" in data and isinstance(data["scores"], list), (
        f"Sidecar must output {{scores: number[]}}; got: {data}"
    )
    assert len(data["scores"]) == 2, f"Expected 2 scores, got {len(data['scores'])}"
    assert all(isinstance(s, (int, float)) for s in data["scores"]), (
        f"All scores must be numbers; got: {data['scores']}"
    )


def test_ac4_fallback_when_onnx_absent():
    """AC4: Falls back to sidecar when ONNX model unavailable, no caller changes needed"""
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
    assert data["ok"], f"Must return scores even when ONNX unavailable: {data}"


def test_ac4_fallback_english_ordering():
    """AC4: Sidecar fallback produces correct English score ordering"""
    script = """
import { createReranker } from './src/rerank/index.js';
const r = createReranker();
const scores = await r.rerank(
  'What is the capital of France?',
  ['Paris is the capital of France', 'The Eiffel Tower was built in 1889']
);
process.stdout.write(JSON.stringify({ scores, correct: scores[0] > scores[1] }));
"""
    out, err, rc = _run_node(script, env=FORCE_SIDECAR_ENV)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["correct"], (
        f"Capital chunk must score higher than Eiffel Tower chunk; got {data['scores']}"
    )


# --- AC5: Factory resolution point ---

def test_ac5_create_reranker_returns_bge():
    """AC5: createReranker() returns a BgeRerankerV2M3 instance"""
    script = """
import { createReranker } from './src/rerank/index.js';
import { BgeRerankerV2M3 } from './src/rerank/BgeRerankerV2M3.js';
const r = createReranker();
process.stdout.write(JSON.stringify({ isBge: r instanceof BgeRerankerV2M3 }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["isBge"], "createReranker() must return BgeRerankerV2M3 instance"


def test_ac5_swapping_requires_only_index_change():
    """AC5: No files outside src/rerank/ import BgeRerankerV2M3 directly"""
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
        f"BgeRerankerV2M3 must only be referenced in src/rerank/: {outside_rerank}"
    )


# --- AC6: Thai language scoring ---

def test_ac6_thai_pair_correct_ordering():
    """AC6: Thai direct-answer chunk scores higher than tangential chunk"""
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
process.stdout.write(JSON.stringify({ scores, correct: scores[0] > scores[1] }));
"""
    out, err, rc = _run_node(script, env=FORCE_SIDECAR_ENV)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["correct"], (
        f"Thai capital chunk must score higher than temple chunk; got {data['scores']}"
    )


def test_ac6_thai_scores_non_negative():
    """AC6: Thai chunk scores are non-negative numbers"""
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
const allNonNeg = scores.every(s => typeof s === 'number' && s >= 0);
process.stdout.write(JSON.stringify({ scores, allNonNeg }));
"""
    out, err, rc = _run_node(script, env=FORCE_SIDECAR_ENV)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["allNonNeg"], f"Thai scores must be non-negative; got {data['scores']}"


# --- AC7: No leakage outside src/rerank/ ---

def test_ac7_embedder_clean():
    """AC7: Embedder module contains no reranker logic"""
    embedder_path = os.path.join(REPO_ROOT, "src", "embeddings", "index.js")
    with open(embedder_path) as fh:
        src = fh.read()
    assert "rerank" not in src.lower(), "Embedder must not contain reranker logic"


def test_ac7_store_index_clean():
    """AC7: Store index module contains no reranker logic"""
    store_path = os.path.join(REPO_ROOT, "src", "store", "index.js")
    with open(store_path) as fh:
        src = fh.read()
    assert "rerank" not in src.lower(), "Store index must not contain reranker logic"


def test_ac7_mock_store_clean():
    """AC7: MockStore contains no reranker logic"""
    path = os.path.join(REPO_ROOT, "src", "store", "MockStore.js")
    with open(path) as fh:
        src = fh.read()
    assert "rerank" not in src.lower(), "MockStore must not contain reranker logic"


# --- AC8: Integration with search pipeline ---

def test_ac8_search_with_rerank_enabled():
    """AC8: searchDocuments with rerankEnabled=true completes without error"""
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
    assert data["ok"], "searchDocuments with rerankEnabled must return array"


def test_ac8_search_imports_rerank():
    """AC8: Search pipeline calls src/rerank/ (not inline implementation)"""
    search_path = os.path.join(REPO_ROOT, "src", "search", "index.js")
    with open(search_path) as fh:
        src = fh.read()
    assert "../rerank" in src, (
        "src/search/index.js must import from ../rerank/ (not inline reranker logic)"
    )
