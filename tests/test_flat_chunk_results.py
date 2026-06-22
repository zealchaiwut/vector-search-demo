"""
Tests for flat chunk-level search results (one API row per chunk).
"""

import json
import os
import re
import subprocess

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEARCH_INDEX_JS = os.path.join(REPO_ROOT, "src", "search", "index.js")
FLATTEN_JS = os.path.join(REPO_ROOT, "src", "search", "flattenResults.js")
SEARCH_EXACT_JS = os.path.join(REPO_ROOT, "src", "core", "searchExact.js")
INDEX_HTML = os.path.join(REPO_ROOT, "public", "index.html")


def _run_node(script, timeout=30):
    result = subprocess.run(
        ["node", "--input-type=module"],
        input=script,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=timeout,
    )
    return result.stdout, result.stderr, result.returncode


def test_flatten_module_exists():
    assert os.path.isfile(FLATTEN_JS), "flattenResults.js must exist"


def test_search_index_uses_flatten():
    with open(SEARCH_INDEX_JS) as f:
        src = f.read()
    assert "flattenChunkResults" in src, "search/index.js must flatten grouped results"
    assert "flattenChunkResults(grouped)" in src


def test_search_exact_uses_flatten():
    with open(SEARCH_EXACT_JS) as f:
        src = f.read()
    assert "flattenChunkResults" in src, "searchExact.js must flatten keyword results"


def test_flatten_sorts_globally_by_score():
    script = """
import { flattenChunkResults } from './src/search/flattenResults.js';
const grouped = [
  {
    id: 'a1',
    headline: 'Doc A',
    score: 0.9,
    attachment_url: null,
    passages: [{ text: 'high', score: 0.9, context: { before: '', after: '' } }],
    chunks: [
      { text: 'high', score: 0.9, chunk_index: 0 },
      { text: 'mid', score: 0.5, chunk_index: 1 },
    ],
  },
  {
    id: 'b1',
    headline: 'Doc B',
    score: 0.7,
    attachment_url: null,
    passages: [{ text: 'between', score: 0.7, context: { before: '', after: '' } }],
    chunks: [{ text: 'between', score: 0.7, chunk_index: 0 }],
  },
];
const flat = flattenChunkResults(grouped);
process.stdout.write(JSON.stringify(flat.map((r) => ({ id: r.article_id, score: r.score }))));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, err
    rows = json.loads(out)
    assert len(rows) == 3
    assert rows[0]["score"] == 0.9
    assert rows[1]["score"] == 0.7
    assert rows[2]["score"] == 0.5


def test_flatten_row_has_chunk_fields():
    script = """
import { flattenChunkResults } from './src/search/flattenResults.js';
const flat = flattenChunkResults([{
  id: 'art-1',
  headline: 'Title',
  score: 0.4,
  attachment_url: '/x',
  passages: [{ text: 'chunk body', score: 0.4, context: { before: '', after: '' } }],
  chunks: [{ text: 'chunk body', score: 0.4, chunk_index: 2 }],
}]);
process.stdout.write(JSON.stringify(flat[0]));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, err
    row = json.loads(out)
    for key in ("article_id", "chunk_index", "text", "score", "headline", "passages", "chunks"):
        assert key in row, f"flat row missing {key}"
    assert row["article_id"] == "art-1"
    assert row["chunk_index"] == 2
    assert len(row["chunks"]) == 1


def test_ui_flat_chunk_cards_and_display_cap():
    with open(INDEX_HTML) as f:
        src = f.read()
    assert re.search(r"DISPLAY_CAP\s*=\s*20", src), "UI must cap displayed chunk rows at 20"
    assert "renderFlatChunkCard" in src, "UI must render one card per flat chunk row"
    assert "capResultRows" in src, "UI must cap result rows before rendering"
    assert "formatResultStatus" in src, "UI must show 'N of M results' when capped"


def test_ui_view_full_on_flat_chunk_cards():
    with open(INDEX_HTML) as f:
        src = f.read()
    assert src.count("View full article") >= 2, (
        "Flat chunk cards must include View full article on search and compare paths"
    )
