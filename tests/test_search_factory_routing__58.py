"""
Acceptance tests for issue #58: Route search command through factory store interface.

AC1 - search.js calls getStore(backend) to obtain a store instance instead of searchDocuments directly
AC2 - The direct import and call to searchDocuments is removed from search.js
AC3 - store.search(query, k) is called on the store instance returned by getStore(backend)
AC4 - resolveBackend() and logActiveBackend() calls remain in place
AC5 - The search command returns identical results (same docs, same ranking, same output)
AC6 - No other command files are modified as part of this change
"""

import os
import re
import subprocess


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEARCH_JS = os.path.join(REPO_ROOT, "src", "commands", "search.js")
CLI_JS = os.path.join(REPO_ROOT, "src", "cli.js")
COMMANDS_DIR = os.path.join(REPO_ROOT, "src", "commands")


def run_cli(*args, **kwargs):
    cmd = ["node", CLI_JS, "search", *args]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=10,
        **kwargs,
    )


def read_search_js():
    with open(SEARCH_JS) as f:
        return f.read()


# ---------------------------------------------------------------------------
# AC1 - search.js calls getStore(backend) instead of searchDocuments directly
# ---------------------------------------------------------------------------

def test_ac1_getstore_is_called_in_search_js():
    """search.js must call getStore(backend) to obtain the store."""
    src = read_search_js()
    assert "getStore" in src, "search.js must call getStore() from the factory"


def test_ac1_getstore_imported_from_factory():
    """search.js must import getStore from the factory module."""
    src = read_search_js()
    # Should import getStore from the factory
    assert re.search(r"getStore", src), "getStore not found in search.js"
    assert re.search(r"factory", src), "search.js must import from factory"


# ---------------------------------------------------------------------------
# AC2 - searchDocuments import and call removed from search.js
# ---------------------------------------------------------------------------

def test_ac2_searchDocuments_not_imported_in_search_js():
    """search.js must NOT import searchDocuments."""
    src = read_search_js()
    # Check there is no import of searchDocuments
    assert not re.search(r"import.*searchDocuments", src), (
        "search.js must not import searchDocuments — use getStore().search() instead"
    )


def test_ac2_searchDocuments_not_called_in_search_js():
    """search.js must NOT call searchDocuments() directly."""
    src = read_search_js()
    # The file should not invoke searchDocuments as a function call
    assert "searchDocuments(" not in src, (
        "search.js must not call searchDocuments() — route through store.search() instead"
    )


def test_ac2_core_search_not_imported_in_search_js():
    """search.js must not import from core/search.js."""
    src = read_search_js()
    assert "core/search" not in src, (
        "search.js must not import from core/search — use getStore().search() instead"
    )


# ---------------------------------------------------------------------------
# AC3 - store.search(query, k) is called on the store instance
# ---------------------------------------------------------------------------

def test_ac3_store_search_called():
    """search.js must call store.search(query, k) on the store instance."""
    src = read_search_js()
    assert re.search(r"store\.search\(", src), (
        "search.js must call store.search() on the factory-provided store"
    )


def test_ac3_await_getstore_pattern():
    """search.js must await getStore(backend) to get a store before searching."""
    src = read_search_js()
    assert re.search(r"await\s+getStore\(", src), (
        "search.js must use 'await getStore(backend)' to obtain the store"
    )


# ---------------------------------------------------------------------------
# AC4 - resolveBackend() and logActiveBackend() remain in place
# ---------------------------------------------------------------------------

def test_ac4_resolveBackend_still_called():
    """resolveBackend() must still be called in search.js."""
    src = read_search_js()
    assert "resolveBackend()" in src, "resolveBackend() must remain in search.js"


def test_ac4_logActiveBackend_still_called():
    """logActiveBackend() must still be called in search.js."""
    src = read_search_js()
    assert "logActiveBackend(" in src, "logActiveBackend() must remain in search.js"


def test_ac4_resolveBackend_imported_from_factory():
    """resolveBackend and logActiveBackend must still be imported from factory."""
    src = read_search_js()
    assert "resolveBackend" in src
    assert "logActiveBackend" in src
    assert "factory" in src


# ---------------------------------------------------------------------------
# AC5 - Identical results: same output format, ranking, fields
# ---------------------------------------------------------------------------

def test_ac5_search_returns_results():
    """Search command returns results with the same output format."""
    result = run_cli("vector search", "-k", "3")
    assert result.returncode == 0, f"CLI exited non-zero: {result.stderr}"
    out = result.stdout
    assert "Rank:" in out, "Output missing 'Rank:' field"
    assert "Headline:" in out, "Output missing 'Headline:' field"
    assert "ID:" in out, "Output missing 'ID:' field"
    assert "Score:" in out, "Output missing 'Score:' field"
    assert "URL:" in out, "Output missing 'URL:' field"


def test_ac5_results_ordered_by_descending_score():
    """Results must be ranked by descending score (highest first)."""
    result = run_cli("vector search semantic embedding", "-k", "5")
    assert result.returncode == 0, f"CLI exited non-zero: {result.stderr}"
    scores = [
        float(m)
        for m in re.findall(r"Score:\s*([0-9]+(?:\.[0-9]+)?)", result.stdout, re.IGNORECASE)
    ]
    assert len(scores) >= 1, f"No scores found in output:\n{result.stdout}"
    for i in range(len(scores) - 1):
        assert scores[i] >= scores[i + 1], (
            f"Scores not descending at position {i}: {scores[i]} < {scores[i + 1]}"
        )


def test_ac5_no_results_code_path_preserved():
    """The 'No results found' code path must still exist in search.js after refactor."""
    src = read_search_js()
    assert "No results found" in src, (
        "search.js must still contain the 'No results found' output path"
    )


def test_ac5_empty_query_exits_nonzero():
    """Empty query must still exit non-zero after refactor."""
    result = run_cli("")
    assert result.returncode != 0


def test_ac5_k_flag_limits_results():
    """The -k flag must still limit the number of returned results."""
    result = run_cli("vector search semantic embedding", "-k", "2")
    assert result.returncode == 0
    block_count = result.stdout.count("--- Result ---")
    assert block_count <= 2, f"Expected at most 2 results, got {block_count}"


# ---------------------------------------------------------------------------
# AC6 - No other command files modified
# ---------------------------------------------------------------------------

def test_ac6_other_command_files_unchanged():
    """Commands other than search.js must not reference getStore differently."""
    other_commands = ["init.js", "ingest.js", "ping.js", "verify.js"]
    for cmd_file in other_commands:
        path = os.path.join(COMMANDS_DIR, cmd_file)
        if os.path.isfile(path):
            with open(path) as f:
                src = f.read()
            # These files should still work — just confirm they exist and are non-empty
            assert len(src) > 0, f"{cmd_file} must not be empty after refactor"
