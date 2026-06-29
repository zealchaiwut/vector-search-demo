"""
Tests for issue #118: _searchMilvus does not group chunk hits by parent article.

Context: The Milvus backend stores chunk-level rows with IDs like articleId:0,
articleId:1, etc. Before this fix, _searchMilvus in src/search/index.js relied on
milvus-store.js to collapse to one chunk per article at the store level, which meant:
  - Only one chunk per article was ever returned (no multi-chunk support)
  - The maxChunks parameter was silently ignored
  - passages[] always had exactly one entry

The fix mirrors _searchFile and _searchPostgres: milvus-store.js.search() returns
raw chunk hits, and _searchMilvus groups them using the same byArticleId Map pattern.

AC1 - _searchMilvus parses chunk IDs via id.split(":")[0] to derive the parent
      article ID, exactly mirroring the _searchFile approach
AC2 - Results are grouped by parent article; each article appears at most once —
      the id field on each result is article-level (no ":N" suffix)
AC3 - Articles are ordered by their single highest-scoring chunk, descending
AC4 - The maxChunks parameter is applied inside _searchMilvus so each article can
      return up to N chunk hits (not just 1)
AC5 - milvus-store.js search() returns raw chunk-level rows (with original IDs
      like articleId:N), deferring grouping to the search layer
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

MODEL_TIMEOUT = 240


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
    """Extract the text of a named function from JS source (heuristic)."""
    start = src.find(f"async function {fn_name}")
    if start == -1:
        return ""
    # Find the next top-level async function declaration
    next_fn = src.find("\nasync function ", start + 1)
    return src[start:] if next_fn == -1 else src[start:next_fn]


@contextlib.contextmanager
def _patched_milvus_store(mock_content):
    """Temporarily replace milvus-store.js with mock_content, restore on exit."""
    backup = MILVUS_STORE_JS + ".bak_118"
    shutil.copy2(MILVUS_STORE_JS, backup)
    try:
        with open(MILVUS_STORE_JS, "w") as f:
            f.write(mock_content)
        yield
    finally:
        shutil.copy2(backup, MILVUS_STORE_JS)
        os.unlink(backup)


# ---------------------------------------------------------------------------
# AC1 — _searchMilvus splits chunk IDs to derive article IDs
# ---------------------------------------------------------------------------


def test_ac1_searchmilvus_splits_chunk_id():
    """AC1: _searchMilvus must parse article IDs via id.split(':')[0]."""
    with open(SEARCH_INDEX_JS) as f:
        src = f.read()
    fn = _extract_function(src, "_searchMilvus")
    assert fn, "_searchMilvus not found in src/search/index.js"
    assert re.search(r'split\s*\(\s*["\']:\s*["\']\)', fn), (
        "_searchMilvus must parse chunk IDs via id.split(':')[0] to derive article IDs, "
        "mirroring the _searchFile pattern"
    )


def test_ac1_searchmilvus_extracts_article_id_from_chunk():
    """AC1: _searchMilvus must reference article-level ID (split on ':')."""
    with open(SEARCH_INDEX_JS) as f:
        src = f.read()
    fn = _extract_function(src, "_searchMilvus")
    assert re.search(r"(articleId|article_id)\s*=.*split", fn), (
        "_searchMilvus must assign the article-level id from id.split(':')[0] "
        "(e.g. const articleId = c.id.split(':')[0])"
    )


# ---------------------------------------------------------------------------
# AC2 — Results grouped by article; each article appears at most once
# ---------------------------------------------------------------------------


def test_ac2_searchmilvus_uses_map_for_grouping():
    """AC2: _searchMilvus must group chunk hits using a Map (byArticleId pattern)."""
    with open(SEARCH_INDEX_JS) as f:
        src = f.read()
    fn = _extract_function(src, "_searchMilvus")
    assert "new Map()" in fn, (
        "_searchMilvus must use 'new Map()' to group chunk hits by article ID, "
        "mirroring the byArticleId Map in _searchFile"
    )


def test_ac2_result_id_is_article_level_in_source():
    """AC2: _searchMilvus return value must use the article-level id, not r.id (chunk id)."""
    with open(SEARCH_INDEX_JS) as f:
        src = f.read()
    fn = _extract_function(src, "_searchMilvus")
    # After the fix, the return block maps `id: articleId`, not `id: r.id`
    # (r.id would be the raw chunk id like articleId:0)
    # Check that we return the grouped articleId
    assert re.search(r"\bid\s*:\s*articleId\b", fn), (
        "_searchMilvus must set 'id: articleId' (article-level) in its return object, "
        "not 'id: r.id' (which would expose the chunk-level id)"
    )


# ---------------------------------------------------------------------------
# AC3 — Articles ordered by highest-scoring chunk, descending
# ---------------------------------------------------------------------------


def test_ac3_searchmilvus_sorts_articles_by_score():
    """AC3: _searchMilvus must sort article groups by their best chunk score."""
    with open(SEARCH_INDEX_JS) as f:
        src = f.read()
    fn = _extract_function(src, "_searchMilvus")
    # Must have a .sort() call that references score (b.score - a.score pattern)
    assert re.search(r"\.sort\s*\(", fn), (
        "_searchMilvus must sort article results so highest-scoring articles come first"
    )
    assert re.search(r"b\..*score\s*-\s*a\..*score|bestChunk\.score", fn), (
        "_searchMilvus must sort by bestChunk score descending (b.bestChunk.score - a.bestChunk.score)"
    )


# ---------------------------------------------------------------------------
# AC4 — maxChunks parameter caps chunk hits per article
# ---------------------------------------------------------------------------


def test_ac4_searchmilvus_applies_maxchunks():
    """AC4: _searchMilvus must use the maxChunks parameter to cap per-article chunks."""
    with open(SEARCH_INDEX_JS) as f:
        src = f.read()
    fn = _extract_function(src, "_searchMilvus")
    assert re.search(r"\.slice\s*\(\s*0\s*,\s*maxChunks\b", fn), (
        "_searchMilvus must apply '.slice(0, maxChunks)' so at most N chunks are "
        "returned per article — the parameter was previously unused"
    )


# ---------------------------------------------------------------------------
# AC5 — milvus-store.js returns raw chunk hits, not pre-collapsed results
# ---------------------------------------------------------------------------


def test_ac5_milvusstore_search_returns_raw_hits():
    """AC5: milvus-store.js search() must return raw chunk rows, not article-collapsed rows."""
    with open(MILVUS_STORE_JS) as f:
        src = f.read()

    # Find the search method body
    search_start = src.find("async search(")
    assert search_start != -1, "milvus-store.js must have an async search() method"

    # Find the end of the search method by counting braces
    depth = 0
    pos = search_start
    while pos < len(src):
        if src[pos] == "{":
            depth += 1
        elif src[pos] == "}":
            depth -= 1
            if depth == 0:
                break
        pos += 1
    search_body = src[search_start:pos + 1]

    # After the fix, search() should NOT collapse to best-chunk-per-article.
    # It should NOT have 'new Map()' for grouping inside the search method.
    assert "new Map()" not in search_body, (
        "milvus-store.js search() must NOT collapse results to one-per-article. "
        "Grouping belongs in _searchMilvus (in src/search/index.js), "
        "not in the store layer. Remove the byArticleId Map from search()."
    )


def test_ac5_milvusstore_search_preserves_chunk_ids():
    """AC5: milvus-store.js search() must preserve original chunk IDs (e.g. articleId:0)."""
    with open(MILVUS_STORE_JS) as f:
        src = f.read()
    search_start = src.find("async search(")
    assert search_start != -1

    # After the fix the return from hits should map id: hit.id (not articleId)
    # The collapse path maps `id: articleId` (a split result) — verify it's removed
    search_section = src[search_start : search_start + 500]
    # If there's still a 'const articleId = hit.id.split' inside search(), it's not fixed
    assert "articleId = hit.id.split" not in search_section, (
        "milvus-store.js search() must not split chunk IDs to get articleId; "
        "the raw chunk id (e.g. 'articleId:0') must be returned so _searchMilvus can group"
    )


# ---------------------------------------------------------------------------
# Dynamic integration test — mock store returning chunk-level rows
# ---------------------------------------------------------------------------

# Minimal mock MilvusStore: no real SDK, returns hard-coded chunk rows.
_MOCK_STORE = """\
export class MilvusStore {
  constructor(address) {}
  async search(queryVector, k) {
    // 3 chunk rows: 2 for article-alpha, 1 for article-beta
    return [
      { id: 'article-alpha:0', headline: 'Alpha Article', details: 'Alpha chunk zero content.', attachment_url: null, score: 0.9 },
      { id: 'article-beta:0',  headline: 'Beta Article',  details: 'Beta chunk zero content.',  attachment_url: null, score: 0.85 },
      { id: 'article-alpha:1', headline: 'Alpha Article', details: 'Alpha chunk one content.',  attachment_url: null, score: 0.7 },
    ];
  }
}
"""

_DYNAMIC_SCRIPT = """\
import { searchDocuments } from './src/search/index.js';
const results = await searchDocuments('test query', 10, 3, null, false);
process.stdout.write(JSON.stringify(results));
"""


def test_ac2_dynamic_correct_article_count():
    """AC2 (dynamic): mock has 2 distinct articles; both appear in results.

    searchDocuments returns flat chunk rows (one per chunk via flattenChunkResults),
    so article-alpha appears twice (2 chunks) and article-beta once.  The important
    check is that ALL distinct articles are present and IDs are article-level.
    """
    with _patched_milvus_store(_MOCK_STORE):
        out, err, rc = _run_node(_DYNAMIC_SCRIPT, env_extra={"MILVUS_HOST": "mock-host"})

    assert rc == 0, f"searchDocuments threw (rc={rc}):\n{err}"
    results = json.loads(out)
    ids = [r.get("id") for r in results]
    assert "article-alpha" in ids, (
        "article-alpha must appear in flat results after Milvus grouping fix"
    )
    assert "article-beta" in ids, (
        "article-beta must appear in flat results"
    )
    # article-alpha has 2 chunks → 2 flat rows; article-beta has 1 → 1 flat row
    assert ids.count("article-alpha") == 2, (
        f"article-alpha must have 2 flat rows (2 chunks), got {ids.count('article-alpha')}: {ids}"
    )


def test_ac2_dynamic_result_ids_are_article_level():
    """AC2 (dynamic): result ids must not contain ':N' chunk suffix."""
    with _patched_milvus_store(_MOCK_STORE):
        out, err, rc = _run_node(_DYNAMIC_SCRIPT, env_extra={"MILVUS_HOST": "mock-host"})

    assert rc == 0, f"searchDocuments threw (rc={rc}):\n{err}"
    results = json.loads(out)
    assert len(results) >= 1, "Expected at least 1 grouped result"
    for r in results:
        rid = str(r.get("id", ""))
        assert ":" not in rid, (
            f"Result id '{rid}' still looks like a chunk id; "
            "_searchMilvus must group to article level"
        )


def test_ac3_dynamic_results_ordered_by_best_score():
    """AC3 (dynamic): results must be sorted by their best chunk score descending."""
    with _patched_milvus_store(_MOCK_STORE):
        out, err, rc = _run_node(_DYNAMIC_SCRIPT, env_extra={"MILVUS_HOST": "mock-host"})

    assert rc == 0, f"searchDocuments threw (rc={rc}):\n{err}"
    results = json.loads(out)
    if len(results) < 2:
        pytest.skip("Need at least 2 results to verify ordering")
    scores = [r.get("score", 0) for r in results]
    for i in range(len(scores) - 1):
        assert scores[i] >= scores[i + 1], (
            f"Results not ordered by best chunk score: scores={scores}"
        )


def test_ac4_dynamic_article_alpha_has_two_flat_rows():
    """AC4 (dynamic): article-alpha has 2 flat rows because it matched 2 chunks.

    searchDocuments returns one flat row per chunk (via flattenChunkResults).
    article-alpha has 2 chunks in the mock data; before the fix only 1 chunk
    was surfaced because milvus-store.js collapsed to best-chunk-per-article.
    """
    with _patched_milvus_store(_MOCK_STORE):
        out, err, rc = _run_node(_DYNAMIC_SCRIPT, env_extra={"MILVUS_HOST": "mock-host"})

    assert rc == 0, f"searchDocuments threw (rc={rc}):\n{err}"
    results = json.loads(out)
    alpha_rows = [r for r in results if r.get("id") == "article-alpha"]
    assert len(alpha_rows) >= 2, (
        f"article-alpha must produce 2 flat rows (one per chunk, maxChunks=3) "
        f"after the grouping fix; got {len(alpha_rows)} rows. "
        "Before the fix, the store collapse meant only 1 chunk was ever returned."
    )
    # Verify the two rows have distinct chunk_index values
    chunk_indices = {r.get("chunk_index") for r in alpha_rows}
    assert len(chunk_indices) >= 2, (
        f"The 2 article-alpha rows must have distinct chunk_index values; got {chunk_indices}"
    )
