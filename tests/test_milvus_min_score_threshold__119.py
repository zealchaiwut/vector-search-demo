"""
Tests for issue #119: Milvus search path uses score>0 threshold instead of MIN_SCORE_THRESHOLD.

Context: sprint-11 review of #103 identified that _searchMilvus filtered candidates
with `r.score > 0` while _searchFile and _searchPostgres both use the module-level
constant MIN_SCORE_THRESHOLD = 0.1.  This inconsistency means the Milvus backend
could return noisier, low-relevance results (score in (0, 0.1)) that the other
backends would discard.

Implied ACs (from the issue body):
  AC1 - _searchMilvus must NOT use the literal `score > 0` filter; the old filter
        string `candidates.filter((r) => r.score > 0)` must be absent from the source.
  AC2 - _searchMilvus must apply MIN_SCORE_THRESHOLD (= 0.1) as the filter threshold,
        consistent with _searchFile and _searchPostgres.
  AC3 - Results whose best-chunk score is < MIN_SCORE_THRESHOLD are excluded.
  AC4 - Results whose best-chunk score is exactly MIN_SCORE_THRESHOLD (>= boundary)
        are included.
"""

import contextlib
import json
import os
import re
import shutil
import subprocess

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEARCH_INDEX_JS = os.path.join(REPO_ROOT, "src", "search", "index.js")
MILVUS_STORE_JS = os.path.join(REPO_ROOT, "src", "store", "milvus-store.js")
EMBEDDINGS_JS = os.path.join(REPO_ROOT, "src", "embeddings", "index.js")

MODEL_TIMEOUT = 240

# Minimal mock embedder — returns fixed-length zero vectors; no @xenova/transformers needed.
_MOCK_EMBEDDER = """\
export const EMBEDDING_DIM = 384;
export const EMBEDDING_MODEL = 'mock-model';
export const MODEL_SPARSE = false;
export async function createEmbedder() {
  return {
    dim: 384,
    sparse: false,
    modelName: 'mock-model',
    _pipelineInitCount: 1,
    async embed(texts) {
      return texts.map(() => Array(384).fill(0));
    },
    async embedSparse(texts) {
      return texts.map(() => ({}));
    },
  };
}
"""


def _run_node(script, env_extra=None, timeout=MODEL_TIMEOUT):
    env = os.environ.copy()
    env.pop("MILVUS_HOST", None)
    env.pop("DB_BACKEND", None)
    if env_extra:
        env.update(env_extra)
    result = subprocess.run(
        ["node", "--input-type=module"],
        input=script,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=env,
        timeout=timeout,
    )
    return result.stdout, result.stderr, result.returncode


def _extract_function(src, fn_name):
    """Extract the text of a named async function from JS source (heuristic)."""
    start = src.find(f"async function {fn_name}")
    if start == -1:
        return ""
    next_fn = src.find("\nasync function ", start + 1)
    return src[start:] if next_fn == -1 else src[start:next_fn]


@contextlib.contextmanager
def _patched_milvus_store(mock_store_content):
    """Temporarily replace milvus-store.js and embeddings/index.js with mocks."""
    store_backup = MILVUS_STORE_JS + ".bak_119"
    embed_backup = EMBEDDINGS_JS + ".bak_119"
    shutil.copy2(MILVUS_STORE_JS, store_backup)
    shutil.copy2(EMBEDDINGS_JS, embed_backup)
    try:
        with open(MILVUS_STORE_JS, "w") as f:
            f.write(mock_store_content)
        with open(EMBEDDINGS_JS, "w") as f:
            f.write(_MOCK_EMBEDDER)
        yield
    finally:
        shutil.copy2(store_backup, MILVUS_STORE_JS)
        shutil.copy2(embed_backup, EMBEDDINGS_JS)
        os.unlink(store_backup)
        os.unlink(embed_backup)


# ---------------------------------------------------------------------------
# AC1 — Old literal `score > 0` filter must be absent
# ---------------------------------------------------------------------------


def test_ac1_old_score_gt_zero_filter_removed():
    """AC1: The old `candidates.filter((r) => r.score > 0)` must not appear in _searchMilvus."""
    with open(SEARCH_INDEX_JS) as f:
        src = f.read()
    fn = _extract_function(src, "_searchMilvus")
    assert fn, "_searchMilvus not found in src/search/index.js"
    assert "score > 0" not in fn, (
        "_searchMilvus must not use 'score > 0' as its filter threshold — "
        "this is the old inconsistent filter that issue #119 replaces with MIN_SCORE_THRESHOLD"
    )


# ---------------------------------------------------------------------------
# AC2 — _searchMilvus must apply MIN_SCORE_THRESHOLD
# ---------------------------------------------------------------------------


def test_ac2_searchmilvus_references_min_score_threshold():
    """AC2: _searchMilvus must reference MIN_SCORE_THRESHOLD for score filtering."""
    with open(SEARCH_INDEX_JS) as f:
        src = f.read()
    fn = _extract_function(src, "_searchMilvus")
    assert fn, "_searchMilvus not found in src/search/index.js"
    assert "MIN_SCORE_THRESHOLD" in fn, (
        "_searchMilvus must use the module-level constant MIN_SCORE_THRESHOLD "
        "to filter candidates, matching _searchFile and _searchPostgres behavior"
    )


def test_ac2_min_score_threshold_is_0_1():
    """AC2: MIN_SCORE_THRESHOLD must be declared as 0.1 in the module."""
    with open(SEARCH_INDEX_JS) as f:
        src = f.read()
    match = re.search(r"const\s+MIN_SCORE_THRESHOLD\s*=\s*([\d.]+)", src)
    assert match, "MIN_SCORE_THRESHOLD constant not found in src/search/index.js"
    assert float(match.group(1)) == pytest.approx(0.1), (
        f"MIN_SCORE_THRESHOLD must be 0.1, got {match.group(1)}"
    )


def test_ac2_threshold_applied_with_gte_operator():
    """AC2: The threshold comparison must use >= (not >) so the boundary is included."""
    with open(SEARCH_INDEX_JS) as f:
        src = f.read()
    fn = _extract_function(src, "_searchMilvus")
    assert fn, "_searchMilvus not found in src/search/index.js"
    assert re.search(r">=\s*MIN_SCORE_THRESHOLD", fn), (
        "_searchMilvus must compare with '>= MIN_SCORE_THRESHOLD' (not '>') "
        "so a result with score exactly equal to the threshold is included"
    )


# ---------------------------------------------------------------------------
# AC3 — Results below threshold are excluded (dynamic)
# ---------------------------------------------------------------------------

# Mock store with one below-threshold result (score 0.05 < 0.1) and one
# above-threshold result (score 0.9).
_MOCK_STORE_AC3 = """\
export class MilvusStore {
  constructor(address) {}
  async search(queryVector, k) {
    return [
      { id: 'good-article:0',  headline: 'Good Article',  details: 'Good content.',  attachment_url: null, score: 0.9 },
      { id: 'noisy-article:0', headline: 'Noisy Article', details: 'Noisy content.', attachment_url: null, score: 0.05 },
    ];
  }
}
"""

_SEARCH_SCRIPT = """\
import { searchDocuments } from './src/search/index.js';
const results = await searchDocuments('test query', 10, 3, null, false);
process.stdout.write(JSON.stringify(results));
"""


def test_ac3_below_threshold_result_excluded():
    """AC3: A result with score 0.05 (< MIN_SCORE_THRESHOLD 0.1) must be excluded."""
    with _patched_milvus_store(_MOCK_STORE_AC3):
        out, err, rc = _run_node(_SEARCH_SCRIPT, env_extra={"MILVUS_HOST": "mock-host"})

    assert rc == 0, f"searchDocuments threw (rc={rc}):\n{err}"
    results = json.loads(out)
    ids = [r.get("id") for r in results]
    assert "noisy-article" not in ids, (
        "noisy-article has score 0.05 < MIN_SCORE_THRESHOLD (0.1) and must be "
        "excluded from Milvus search results — the old 'score > 0' filter would "
        "have incorrectly included it"
    )


def test_ac3_above_threshold_result_included():
    """AC3: A result with score 0.9 (>= MIN_SCORE_THRESHOLD) must be included."""
    with _patched_milvus_store(_MOCK_STORE_AC3):
        out, err, rc = _run_node(_SEARCH_SCRIPT, env_extra={"MILVUS_HOST": "mock-host"})

    assert rc == 0, f"searchDocuments threw (rc={rc}):\n{err}"
    results = json.loads(out)
    ids = [r.get("id") for r in results]
    assert "good-article" in ids, (
        "good-article has score 0.9 >= MIN_SCORE_THRESHOLD (0.1) and must appear "
        "in Milvus search results"
    )


# ---------------------------------------------------------------------------
# AC4 — Result at exactly the threshold boundary is included (dynamic)
# ---------------------------------------------------------------------------

_MOCK_STORE_AC4 = """\
export class MilvusStore {
  constructor(address) {}
  async search(queryVector, k) {
    return [
      { id: 'boundary-article:0', headline: 'Boundary Article', details: 'Exactly at threshold.', attachment_url: null, score: 0.1 },
    ];
  }
}
"""


def test_ac4_result_at_exact_threshold_included():
    """AC4: A result with score exactly 0.1 (== MIN_SCORE_THRESHOLD) must be included."""
    with _patched_milvus_store(_MOCK_STORE_AC4):
        out, err, rc = _run_node(_SEARCH_SCRIPT, env_extra={"MILVUS_HOST": "mock-host"})

    assert rc == 0, f"searchDocuments threw (rc={rc}):\n{err}"
    results = json.loads(out)
    ids = [r.get("id") for r in results]
    assert "boundary-article" in ids, (
        "boundary-article has score exactly 0.1 == MIN_SCORE_THRESHOLD and must be "
        "included ('>= threshold' boundary condition) — the old 'score > 0' filter "
        "would have included it, but a strict '> 0.1' would not"
    )
