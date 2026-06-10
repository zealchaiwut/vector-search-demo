"""Tests for issue #7: Wire CLI search command to searchDocuments core (runs against UAT)"""
import os
import subprocess
import sys

import httpx
import pytest

UAT_BASE_URL = os.environ.get("UAT_BASE_URL", "http://localhost:8001")

# Coder repo path — UAT server runs from here; CLI is also here
CODER_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "coder")
)
CLI_PATH = os.path.join(CODER_DIR, "src", "cli.js")
SEARCH_CMD_PATH = os.path.join(CODER_DIR, "src", "commands", "search.js")
CORE_SEARCH_PATH = os.path.join(CODER_DIR, "src", "core", "search.js")


def run_cli(*args, **kwargs):
    """Run `node src/cli.js search <args>` from coder dir; return CompletedProcess."""
    return subprocess.run(
        ["node", CLI_PATH, "search", *args],
        capture_output=True,
        text=True,
        cwd=CODER_DIR,
        timeout=10,
        **kwargs,
    )


@pytest.fixture
def client():
    with httpx.Client(base_url=UAT_BASE_URL, timeout=10.0) as c:
        yield c


# --- AC1: search.js calls searchDocuments with query and k ---

def test_wire_cli_search_command__search_command_imports_searchdocuments():
    # AC1: src/commands/search.js must import searchDocuments from core
    assert os.path.exists(SEARCH_CMD_PATH), f"search.js not found at {SEARCH_CMD_PATH}"
    with open(SEARCH_CMD_PATH) as f:
        src = f.read()
    assert "searchDocuments" in src, "search.js does not reference searchDocuments"
    assert "core/search" in src, "search.js does not import from core/search"


def test_wire_cli_search_command__search_endpoint_returns_results(client):
    # AC1 via HTTP: /search?q=<query>&k=3 returns results (same searchDocuments logic)
    r = client.get("/search", params={"q": "vector search", "k": "3"})
    assert r.status_code == 200
    data = r.json()
    assert "results" in data
    assert len(data["results"]) > 0


# --- AC2: result block shows rank, title, doc_id, score, attachment ---

def test_wire_cli_search_command__result_block_has_required_fields():
    # AC2: CLI output contains Rank, Title, Doc-ID, Score, Attachment
    result = run_cli("vector search", "-k", "2")
    assert result.returncode == 0, f"CLI exited {result.returncode}: {result.stderr}"
    out = result.stdout
    assert "Rank:" in out, "Output missing 'Rank:' field"
    assert "Title:" in out, "Output missing 'Title:' field"
    assert "Doc-ID:" in out, "Output missing 'Doc-ID:' field"
    assert "Score:" in out, "Output missing 'Score:' field"
    assert "Attachment:" in out, "Output missing 'Attachment:' field"
    assert ".txt" in out, "Attachment field missing .txt extension"


# --- AC3: results ordered by descending score ---

def test_wire_cli_search_command__results_ordered_descending_score(client):
    # AC3: /search results are sorted by score descending
    r = client.get("/search", params={"q": "semantic search embedding"})
    assert r.status_code == 200
    scores = [item["score"] for item in r.json()["results"]]
    assert scores == sorted(scores, reverse=True), "Results not ordered by descending score"


# --- AC4: empty result set prints "No results found" ---

def test_wire_cli_search_command__no_results_message():
    # AC4: nonsense query prints "No results found" and exits 0
    result = run_cli("xyzzy_nonexistent_query_12345", "-k", "5")
    assert result.returncode == 0
    assert "No results found" in result.stdout


# --- AC5: empty/missing query exits non-zero with usage message ---

def test_wire_cli_search_command__empty_query_exits_nonzero():
    # AC5: empty query string → exit code 1, stderr has usage message
    result = run_cli("", "-k", "5")
    assert result.returncode != 0, "Expected non-zero exit for empty query"
    combined = result.stdout + result.stderr
    assert "Usage" in combined or "query is required" in combined.lower()


# --- AC6: commander search "database backup" -k 5 returns ≤ 5 blocks ---

def test_wire_cli_search_command__k_limits_result_count():
    # AC6: -k 5 returns at most 5 result blocks
    result = run_cli("database backup", "-k", "5")
    assert result.returncode == 0
    block_count = result.stdout.count("--- Result ---")
    assert block_count <= 5, f"Expected ≤5 results, got {block_count}"
    # corpus has doc-004 matching "database" → at least 1 result expected
    assert block_count >= 1, "Expected at least 1 result for 'database backup'"


# --- AC7: -k defaults to 10 when omitted ---

def test_wire_cli_search_command__k_defaults_to_10(client):
    # AC7: /search without k param returns up to 10 results
    r = client.get("/search", params={"q": "search"})
    assert r.status_code == 200
    results = r.json()["results"]
    assert len(results) <= 10, f"Default k should limit to 10 results, got {len(results)}"
