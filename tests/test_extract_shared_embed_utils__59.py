"""
Tests for issue #59: Extract shared avgEmbeddings/collapseToArticles to utility module

AC1 - src/store/embedUtils.js exists as the single source of truth for shared
      embedding utility functions.
AC2 - embedUtils.js exports avgEmbeddings and collapseToArticles.
AC3 - src/data/collection.js does NOT define its own avgEmbeddings or
      collapseToArticles (eliminating the duplicate).
AC4 - src/store/postgres.js does NOT define its own avgEmbeddings or
      collapseToArticles (eliminating the duplicate).
AC5 - avgEmbeddings correctly averages a set of equal-length embedding vectors.
AC6 - collapseToArticles correctly merges chunk rows into one entry per article,
      joining details and averaging embeddings.
"""

import os
import re
import importlib.util
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EMBED_UTILS_JS = os.path.join(REPO_ROOT, "src", "store", "embedUtils.js")
COLLECTION_JS = os.path.join(REPO_ROOT, "src", "data", "collection.js")
POSTGRES_JS = os.path.join(REPO_ROOT, "src", "store", "postgres.js")


# ---------------------------------------------------------------------------
# AC1: embedUtils.js exists
# ---------------------------------------------------------------------------


def test_ac1_embed_utils_file_exists():
    """src/store/embedUtils.js must exist as the shared utility module."""
    assert os.path.isfile(EMBED_UTILS_JS), (
        f"src/store/embedUtils.js not found at {EMBED_UTILS_JS}. "
        "This file must exist as the single source of truth for avgEmbeddings "
        "and collapseToArticles (issue #59)."
    )


# ---------------------------------------------------------------------------
# AC2: embedUtils.js exports avgEmbeddings and collapseToArticles
# ---------------------------------------------------------------------------


def test_ac2_embed_utils_exports_avg_embeddings():
    """embedUtils.js must export the avgEmbeddings function."""
    with open(EMBED_UTILS_JS) as f:
        src = f.read()
    assert re.search(r"export\s+function\s+avgEmbeddings", src), (
        "embedUtils.js must export avgEmbeddings as a named export"
    )


def test_ac2_embed_utils_exports_collapse_to_articles():
    """embedUtils.js must export the collapseToArticles function."""
    with open(EMBED_UTILS_JS) as f:
        src = f.read()
    assert re.search(r"export\s+function\s+collapseToArticles", src), (
        "embedUtils.js must export collapseToArticles as a named export"
    )


# ---------------------------------------------------------------------------
# AC3: collection.js does NOT define its own copies
# ---------------------------------------------------------------------------


def test_ac3_collection_js_no_local_avg_embeddings():
    """collection.js must not define its own avgEmbeddings function."""
    with open(COLLECTION_JS) as f:
        src = f.read()
    assert not re.search(r"function\s+avgEmbeddings", src), (
        "collection.js must not define its own avgEmbeddings — "
        "use src/store/embedUtils.js instead (issue #59)"
    )


def test_ac3_collection_js_no_local_collapse_to_articles():
    """collection.js must not define its own collapseToArticles function."""
    with open(COLLECTION_JS) as f:
        src = f.read()
    assert not re.search(r"function\s+collapseToArticles", src), (
        "collection.js must not define its own collapseToArticles — "
        "use src/store/embedUtils.js instead (issue #59)"
    )


# ---------------------------------------------------------------------------
# AC4: postgres.js does NOT define its own copies
# ---------------------------------------------------------------------------


def test_ac4_postgres_js_no_local_avg_embeddings():
    """postgres.js must not define its own avgEmbeddings function."""
    with open(POSTGRES_JS) as f:
        src = f.read()
    assert not re.search(r"function\s+avgEmbeddings", src), (
        "postgres.js must not define its own avgEmbeddings — "
        "use src/store/embedUtils.js instead (issue #59)"
    )


def test_ac4_postgres_js_no_local_collapse_to_articles():
    """postgres.js must not define its own collapseToArticles function."""
    with open(POSTGRES_JS) as f:
        src = f.read()
    assert not re.search(r"function\s+collapseToArticles", src), (
        "postgres.js must not define its own collapseToArticles — "
        "use src/store/embedUtils.js instead (issue #59)"
    )


# ---------------------------------------------------------------------------
# AC5: avgEmbeddings correctness (evaluated via node)
# ---------------------------------------------------------------------------


def _run_node_snippet(snippet: str) -> str:
    """Run a Node.js snippet and return stdout."""
    import subprocess
    result = subprocess.run(
        ["node", "--input-type=module", "-e", snippet],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, (
        f"Node snippet failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    return result.stdout.strip()


def test_ac5_avg_embeddings_averages_correctly():
    """avgEmbeddings must return the element-wise mean of the input vectors."""
    snippet = """
import { avgEmbeddings } from './src/store/embedUtils.js';
const result = avgEmbeddings([[1, 2, 3], [3, 4, 5]]);
console.log(JSON.stringify(result));
"""
    out = _run_node_snippet(snippet)
    result = __import__("json").loads(out)
    assert result == [2, 3, 4], (
        f"avgEmbeddings([[1,2,3],[3,4,5]]) should return [2,3,4], got {result}"
    )


def test_ac5_avg_embeddings_empty_returns_empty():
    """avgEmbeddings([]) must return []."""
    snippet = """
import { avgEmbeddings } from './src/store/embedUtils.js';
const result = avgEmbeddings([]);
console.log(JSON.stringify(result));
"""
    out = _run_node_snippet(snippet)
    result = __import__("json").loads(out)
    assert result == [], (
        f"avgEmbeddings([]) should return [], got {result}"
    )


# ---------------------------------------------------------------------------
# AC6: collapseToArticles correctness (evaluated via node)
# ---------------------------------------------------------------------------


def test_ac6_collapse_to_articles_merges_chunks():
    """collapseToArticles must merge chunk rows into one entry per article."""
    snippet = """
import { collapseToArticles } from './src/store/embedUtils.js';
const rows = [
  { id: 'a1:0', headline: 'Article One', details: 'Hello', attachment_url: '', embedding: [1, 0] },
  { id: 'a1:1', headline: 'Article One', details: 'World', attachment_url: '', embedding: [3, 0] },
  { id: 'a2:0', headline: 'Article Two', details: 'Solo',  attachment_url: '', embedding: [5, 5] },
];
const result = collapseToArticles(rows);
console.log(JSON.stringify(result));
"""
    import json
    out = _run_node_snippet(snippet)
    result = json.loads(out)

    assert len(result) == 2, f"Expected 2 collapsed articles, got {len(result)}"

    a1 = next((r for r in result if r["id"] == "a1"), None)
    assert a1 is not None, "Collapsed result must include article 'a1'"
    assert a1["details"] == "Hello World", (
        f"Details must be joined with space, got: {a1['details']!r}"
    )
    assert a1["embedding"] == [2.0, 0.0], (
        f"Embedding must be averaged across chunks, got: {a1['embedding']}"
    )

    a2 = next((r for r in result if r["id"] == "a2"), None)
    assert a2 is not None, "Collapsed result must include article 'a2'"
    assert a2["details"] == "Solo"
    assert a2["embedding"] == [5.0, 5.0]


def test_ac6_collapse_to_articles_single_chunk_no_average():
    """collapseToArticles on a single chunk must preserve the embedding unchanged."""
    snippet = """
import { collapseToArticles } from './src/store/embedUtils.js';
const rows = [{ id: 'x1:0', headline: 'H', details: 'D', attachment_url: '', embedding: [0.5, 0.5] }];
const result = collapseToArticles(rows);
console.log(JSON.stringify(result));
"""
    import json
    out = _run_node_snippet(snippet)
    result = json.loads(out)
    assert len(result) == 1
    assert result[0]["embedding"] == [0.5, 0.5], (
        f"Single-chunk collapse should preserve embedding exactly, got {result[0]['embedding']}"
    )
