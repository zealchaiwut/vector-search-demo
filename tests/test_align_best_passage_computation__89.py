"""
Tests for issue #89: Align best_passage computation across Postgres and file backends.

Code review of #81 found that _searchPostgres assigns best_passage = passages[0] ?? null
(top chunk's best sentence only), while _searchFile computes best_passage via
selectBestPassage on the full concatenated article text. For long multi-chunk articles the
Postgres path may return a weaker result.

Fix (option b): _searchPostgres computes best_passage via selectBestPassage on the full
assembled article text (via store.get(articleId).details), matching the file backend.
"""

import json
import os
import re
import subprocess

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEARCH_JS = os.path.join(REPO_ROOT, "src", "core", "search.js")

HAS_NODE_MODULES = os.path.isdir(os.path.join(REPO_ROOT, "node_modules"))


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


def _call_search(query, k=3):
    script = f"""
import {{ searchDocuments }} from './src/core/search.js';
const results = await searchDocuments({json.dumps(query)}, {k});
process.stdout.write(JSON.stringify(results));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error (rc={rc}):\n{err}"
    return json.loads(out)


def _read_postgres_fn(src):
    """Return the source text of _searchPostgres from search.js."""
    start = src.find("async function _searchPostgres(")
    if start == -1:
        return ""
    depth = 0
    for i in range(start, len(src)):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[start : i + 1]
    return src[start:]


def _read_file_fn(src):
    """Return the source text of _searchFile from search.js."""
    start = src.find("async function _searchFile(")
    if start == -1:
        return ""
    depth = 0
    for i in range(start, len(src)):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[start : i + 1]
    return src[start:]


# ---------------------------------------------------------------------------
# AC1 — _searchPostgres must not use passages[0] as a shortcut for best_passage
# ---------------------------------------------------------------------------


def test_postgres_path_does_not_shortcut_passages_zero():
    """_searchPostgres must not assign best_passage = passages[0] ?? null."""
    with open(SEARCH_JS) as f:
        src = f.read()
    pg = _read_postgres_fn(src)
    assert pg, "_searchPostgres not found in search.js"
    assert not re.search(r"best_passage\s*=\s*passages\s*\[\s*0\s*\]", pg), (
        "_searchPostgres must not assign best_passage = passages[0]; "
        "compute it via selectBestPassage on full article text instead"
    )


# ---------------------------------------------------------------------------
# AC2 — _searchPostgres must call selectBestPassage for its own best_passage
# ---------------------------------------------------------------------------


def test_postgres_path_calls_select_best_passage():
    """_searchPostgres must call selectBestPassage to derive best_passage."""
    with open(SEARCH_JS) as f:
        src = f.read()
    pg = _read_postgres_fn(src)
    assert pg, "_searchPostgres not found in search.js"
    calls = re.findall(r"\bselectBestPassage\s*\(", pg)
    # Expect at least 2: one per chunk (for passages[]) and one for best_passage
    assert len(calls) >= 2, (
        f"_searchPostgres must call selectBestPassage at least twice "
        f"(per-chunk passages + best_passage); found {len(calls)}"
    )


# ---------------------------------------------------------------------------
# AC3 — _searchPostgres fetches full article text before computing best_passage
# ---------------------------------------------------------------------------


def test_postgres_path_assembles_full_article_text():
    """_searchPostgres must obtain full article text via store.get or chunk join."""
    with open(SEARCH_JS) as f:
        src = f.read()
    pg = _read_postgres_fn(src)
    assert pg, "_searchPostgres not found in search.js"
    has_store_get = bool(re.search(r"store\.get\s*\(", pg))
    has_concat = bool(
        re.search(r"articleText|articleTexts|allChunks|\.join\s*\(", pg)
    )
    assert has_store_get or has_concat, (
        "_searchPostgres must assemble full article text (via store.get or chunk "
        "concatenation) before passing it to selectBestPassage for best_passage"
    )


# ---------------------------------------------------------------------------
# AC4 — _searchFile already uses selectBestPassage on full text (regression guard)
# ---------------------------------------------------------------------------


def test_file_path_does_not_shortcut_passages_zero():
    """_searchFile must not use passages[0] as best_passage shortcut."""
    with open(SEARCH_JS) as f:
        src = f.read()
    file_fn = _read_file_fn(src)
    assert file_fn, "_searchFile not found in search.js"
    assert not re.search(r"best_passage\s*=\s*passages\s*\[\s*0\s*\]", file_fn), (
        "_searchFile must compute best_passage via selectBestPassage, not passages[0]"
    )


def test_file_path_calls_select_best_passage_for_best_passage():
    """_searchFile must call selectBestPassage to compute best_passage."""
    with open(SEARCH_JS) as f:
        src = f.read()
    file_fn = _read_file_fn(src)
    assert file_fn, "_searchFile not found in search.js"
    assert re.search(r"\bselectBestPassage\s*\(", file_fn), (
        "_searchFile must call selectBestPassage for best_passage"
    )


# ---------------------------------------------------------------------------
# AC5 — runtime: file-backend best_passage has correct shape and non-empty text
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_NODE_MODULES, reason="node_modules not installed")
def test_runtime_best_passage_shape():
    """File-backend best_passage must have text, offsets, and context fields."""
    results = _call_search("vector search semantic embedding", k=3)
    assert results, "Expected at least one result from the file backend"
    for r in results:
        bp = r.get("best_passage")
        assert bp is not None, f"best_passage must not be null for id={r.get('id')}"
        for key in ("text", "start_offset", "end_offset", "context"):
            assert key in bp, (
                f"best_passage missing '{key}' for id={r.get('id')}; "
                f"keys present: {list(bp.keys())}"
            )
        ctx = bp["context"]
        assert "before" in ctx and "after" in ctx, (
            f"best_passage.context must have before/after for id={r.get('id')}"
        )


@pytest.mark.skipif(not HAS_NODE_MODULES, reason="node_modules not installed")
def test_runtime_best_passage_text_nonempty():
    """best_passage.text must be a non-empty string for every result."""
    results = _call_search("semantic search", k=3)
    assert results, "Expected at least one result"
    for r in results:
        bp = r.get("best_passage", {})
        assert bp.get("text", "").strip(), (
            f"best_passage.text must not be blank for id={r.get('id')}"
        )
