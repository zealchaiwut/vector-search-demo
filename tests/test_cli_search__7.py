"""
Acceptance tests for issue #7: Wire CLI search command to searchDocuments core.

AC1 - src/commands/search.js calls searchDocuments with query and k value
AC2 - Each result prints as block: rank, title, doc_id, score, attachment name
AC3 - Results ordered by descending score (rank 1 = highest)
AC4 - Empty result set prints "No results found"
AC5 - Empty/missing query exits non-zero and prints usage message
AC6 - commander search <query> -k 5 prints up to 5 ranked blocks
AC7 - -k defaults to 10 when omitted
"""

import os
import re
import subprocess


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI_JS = os.path.join(REPO_ROOT, "src", "cli.js")
SEARCH_JS = os.path.join(REPO_ROOT, "src", "commands", "search.js")
CORE_SEARCH_JS = os.path.join(REPO_ROOT, "src", "core", "search.js")


def run_cli(*args, **kwargs):
    """Run node src/cli.js search <args> and return CompletedProcess."""
    cmd = ["node", CLI_JS, "search", *args]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# AC1 - File structure: src/commands/search.js imports searchDocuments
# ---------------------------------------------------------------------------

def test_ac1_commands_search_file_exists():
    """src/commands/search.js must exist."""
    assert os.path.isfile(SEARCH_JS), f"Missing: {SEARCH_JS}"


def test_ac1_core_search_file_exports_searchDocuments():
    """src/core/search.js must export searchDocuments."""
    assert os.path.isfile(CORE_SEARCH_JS), f"Missing: {CORE_SEARCH_JS}"
    with open(CORE_SEARCH_JS) as f:
        src = f.read()
    assert "searchDocuments" in src, "searchDocuments not found in core/search.js"


def test_ac1_commands_search_uses_store_search():
    """src/commands/search.js must route search through getStore().search() (issue #58 follow-up)."""
    with open(SEARCH_JS) as f:
        src = f.read()
    assert "getStore" in src, "commands/search.js must call getStore() from factory (issue #58)"
    assert "store.search(" in src, "commands/search.js must call store.search() on factory store"


# ---------------------------------------------------------------------------
# AC2 - Each result block shows rank, headline, id, score, url
# ---------------------------------------------------------------------------

def test_ac2_result_block_contains_required_fields():
    """Each result block must show rank, headline, id, score, url."""
    result = run_cli("vector search", "-k", "1")
    out = result.stdout
    assert result.returncode == 0, f"Non-zero exit: {result.stderr}"
    # rank
    assert re.search(r"rank\s*[:\-]?\s*1", out, re.IGNORECASE), f"Rank not found in:\n{out}"
    # headline
    assert re.search(r"headline\s*[:\-]", out, re.IGNORECASE), f"Headline label not found in:\n{out}"
    # id
    assert re.search(r"\bID\s*[:\-]", out, re.IGNORECASE), f"ID not found in:\n{out}"
    # score
    assert re.search(r"score\s*[:\-]", out, re.IGNORECASE), f"Score not found in:\n{out}"
    # url
    assert re.search(r"url\s*[:\-]", out, re.IGNORECASE), f"URL not found in:\n{out}"


# ---------------------------------------------------------------------------
# AC3 - Results ordered by descending score (rank 1 = highest)
# ---------------------------------------------------------------------------

def test_ac3_results_ordered_by_descending_score():
    """Rank 1 must have the highest score; scores must be non-increasing."""
    result = run_cli("vector search semantic embedding", "-k", "5")
    assert result.returncode == 0, f"Non-zero exit: {result.stderr}"
    out = result.stdout
    scores = [float(m) for m in re.findall(r"score\s*[:\-]\s*([0-9]+\.[0-9]+)", out, re.IGNORECASE)]
    assert len(scores) >= 1, f"No scores found in output:\n{out}"
    for i in range(len(scores) - 1):
        assert scores[i] >= scores[i + 1], (
            f"Scores not descending at position {i}: {scores[i]} < {scores[i+1]}"
        )


# ---------------------------------------------------------------------------
# AC4 - Empty result set prints "No results found"
# ---------------------------------------------------------------------------

def test_ac4_no_results_message():
    """A query that matches nothing prints 'No results found'."""
    result = run_cli("xyzzy_nonexistent_query_12345", "-k", "5")
    assert result.returncode == 0, f"Expected exit 0 for no-match query, got {result.returncode}"
    assert re.search(r"no results found", result.stdout, re.IGNORECASE), (
        f"Expected 'No results found' in:\n{result.stdout}"
    )


# ---------------------------------------------------------------------------
# AC5 - Empty/missing query exits non-zero with usage message
# ---------------------------------------------------------------------------

def test_ac5_empty_query_exits_nonzero():
    """Empty string query must exit non-zero."""
    result = run_cli("")
    assert result.returncode != 0, (
        f"Expected non-zero exit for empty query, got 0. stdout={result.stdout}"
    )


def test_ac5_empty_query_prints_usage():
    """Empty string query must print a usage/error message."""
    result = run_cli("")
    combined = result.stdout + result.stderr
    assert re.search(r"usage|query|required", combined, re.IGNORECASE), (
        f"Expected usage/error message for empty query:\n{combined}"
    )


def test_ac5_missing_query_exits_nonzero():
    """Missing query (no args after search) must exit non-zero."""
    proc = subprocess.run(
        ["node", CLI_JS, "search"],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    assert proc.returncode != 0, (
        f"Expected non-zero exit when query omitted, got 0. stdout={proc.stdout}"
    )


# ---------------------------------------------------------------------------
# AC6 - -k limits result count
# ---------------------------------------------------------------------------

def test_ac6_k_flag_limits_results():
    """With -k 2, at most 2 result blocks are printed."""
    result = run_cli("vector search semantic embedding", "-k", "2")
    assert result.returncode == 0, f"Non-zero exit: {result.stderr}"
    ranks = re.findall(r"rank\s*[:\-]?\s*(\d+)", result.stdout, re.IGNORECASE)
    assert len(ranks) <= 2, f"Expected at most 2 results, got {len(ranks)}: {ranks}"


def test_ac6_k1_prints_exactly_one_result():
    """With -k 1, exactly 1 result block is printed."""
    result = run_cli("vector search", "-k", "1")
    assert result.returncode == 0, f"Non-zero exit: {result.stderr}"
    ranks = re.findall(r"rank\s*[:\-]?\s*(\d+)", result.stdout, re.IGNORECASE)
    assert len(ranks) == 1, f"Expected exactly 1 result, got {len(ranks)}: {result.stdout}"


# ---------------------------------------------------------------------------
# AC7 - -k defaults to 10 when omitted
# ---------------------------------------------------------------------------

def test_ac7_default_k_no_error():
    """`commander search <query>` without -k runs without error."""
    result = run_cli("vector search")
    assert result.returncode == 0, (
        f"Expected exit 0 when -k omitted, got {result.returncode}. stderr={result.stderr}"
    )


def test_ac7_default_k_returns_results():
    """Without -k, results are still returned (up to default 10)."""
    result = run_cli("vector search semantic embedding pipeline")
    assert result.returncode == 0
    ranks = re.findall(r"rank\s*[:\-]?\s*\d+", result.stdout, re.IGNORECASE)
    assert len(ranks) >= 1, f"Expected at least 1 result without -k flag:\n{result.stdout}"


def test_ac7_default_k_at_most_10():
    """Without -k, result count does not exceed 10."""
    result = run_cli("vector search semantic embedding pipeline")
    assert result.returncode == 0
    ranks = re.findall(r"rank\s*[:\-]?\s*\d+", result.stdout, re.IGNORECASE)
    assert len(ranks) <= 10, f"Default k should cap at 10, got {len(ranks)}"
