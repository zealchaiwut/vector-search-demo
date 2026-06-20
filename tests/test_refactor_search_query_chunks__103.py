"""
Tests for issue #103: Refactor search to query chunks and group by article.

AC1 - The search pipeline embeds the incoming query and runs the vector similarity
      search against the chunks table (chunk-level rows), not the articles table
AC2 - Results are grouped by parent article; each article appears at most once
AC3 - Articles are ordered by their single highest-scoring chunk (descending)
AC4 - Each article in the response includes headline and attachment_url from its
      article metadata
AC5 - Each article includes up to N matching chunks, each with text and score,
      sorted by score descending
AC6 - N is configurable (env var SEARCH_MAX_CHUNKS or query parameter n) with a
      documented default
AC7 - A query whose terms appear in multiple sections of the same document returns
      that document with more than one chunk hit in the response
AC8 - All changes are contained within src/search
"""

import json
import os
import re
import subprocess

import httpx
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEARCH_MODULE = os.path.join(REPO_ROOT, "src", "search", "index.js")
CORE_SEARCH = os.path.join(REPO_ROOT, "src", "core", "search.js")

BASE_URL = (
    os.environ.get("UAT_BASE_URL")
    or "http://localhost:" + os.environ.get("UAT_PORT", "8010")
)
HAS_DB = bool(os.environ.get("DATABASE_URL") or os.environ.get("UAT_BASE_URL"))


def _run_node(script, env_extra=None, timeout=60):
    env = os.environ.copy()
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


def _call_search(query, k=5, env_extra=None):
    script = f"""
import {{ searchDocuments }} from './src/search/index.js';
const results = await searchDocuments({json.dumps(query)}, {k});
process.stdout.write(JSON.stringify(results));
"""
    out, err, rc = _run_node(script, env_extra=env_extra)
    assert rc == 0, f"Node error (rc={rc}):\n{err}"
    return json.loads(out)


@pytest.fixture
def client():
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as c:
        yield c


# ---------------------------------------------------------------------------
# AC8 — All changes are contained within src/search
# ---------------------------------------------------------------------------


def test_ac8_search_module_exists():
    """src/search/index.js must exist as the new search module."""
    assert os.path.exists(SEARCH_MODULE), (
        f"Search module must exist at {SEARCH_MODULE}. "
        "All changes for issue #103 must be in src/search/"
    )


def test_ac8_search_module_exports_search_documents():
    """src/search/index.js must export searchDocuments."""
    with open(SEARCH_MODULE) as f:
        src = f.read()
    assert re.search(r"export\s+(async\s+)?function\s+searchDocuments|export\s+\{[^}]*searchDocuments", src), (
        "src/search/index.js must export the searchDocuments function"
    )


# ---------------------------------------------------------------------------
# AC1 — Search pipeline operates at chunk level (chunk rows, split by ':')
# ---------------------------------------------------------------------------


def test_ac1_search_module_handles_chunk_ids():
    """src/search/index.js must split ':'-suffixed ids to derive article ids."""
    with open(SEARCH_MODULE) as f:
        src = f.read()
    assert re.search(r"split\s*\(\s*['\"]:\s*['\"]\)", src) or \
           re.search(r"article_id|articleId", src), (
        "src/search/index.js must handle chunk ids (split by ':') to group results "
        "by parent article — indicating search runs at chunk granularity"
    )


def test_ac1_collection_json_chunk_rows_are_searched():
    """Search must return results when collection.json has chunk rows."""
    collection_path = os.path.join(REPO_ROOT, "collection.json")
    if not os.path.exists(collection_path):
        pytest.skip("collection.json not present")
    with open(collection_path) as f:
        rows = json.load(f)
    chunk_rows = [r for r in rows if ":" in str(r.get("id", ""))]
    if not chunk_rows:
        pytest.skip("No chunk rows in collection.json")
    results = _call_search("vector search embedding", k=5)
    assert len(results) >= 1, (
        "Search must return results when chunk rows exist in collection.json"
    )


# ---------------------------------------------------------------------------
# AC2 — Results grouped by parent article; each article at most once
# ---------------------------------------------------------------------------


def test_ac2_results_deduplicated_by_article():
    """Each article must appear at most once in search results."""
    results = _call_search("vector search embedding", k=10)
    ids = [r.get("id") for r in results]
    assert len(ids) == len(set(ids)), (
        f"Search results must not have duplicate article ids; duplicates: "
        f"{[i for i in ids if ids.count(i) > 1]}"
    )


def test_ac2_result_ids_are_article_level():
    """Result ids must be article-level (no ':N' suffix)."""
    results = _call_search("vector search", k=5)
    for r in results:
        result_id = str(r.get("id", ""))
        assert ":" not in result_id, (
            f"Result id '{result_id}' looks like a chunk id; "
            "results must be grouped to article level"
        )


# ---------------------------------------------------------------------------
# AC3 — Articles ordered by single highest-scoring chunk, descending
# ---------------------------------------------------------------------------


def test_ac3_results_sorted_by_score_descending():
    """Top-level results must be sorted by score descending."""
    results = _call_search("semantic vector search embedding", k=10)
    if len(results) < 2:
        pytest.skip("Need at least 2 results to test sort order")
    scores = [r.get("score", 0) for r in results]
    for i in range(len(scores) - 1):
        assert scores[i] >= scores[i + 1], (
            f"Results not sorted by score descending: scores={scores}"
        )


def test_ac3_article_score_equals_best_chunk_score():
    """Article-level score must equal the best chunk score for that article."""
    results = _call_search("vector search embedding", k=5)
    for r in results:
        chunks = r.get("chunks", [])
        if not chunks:
            continue
        best_chunk_score = max(c["score"] for c in chunks)
        article_score = r.get("score", 0)
        assert abs(article_score - best_chunk_score) < 1e-4, (
            f"Article score {article_score} must equal best chunk score "
            f"{best_chunk_score} for article id={r.get('id')}"
        )


# ---------------------------------------------------------------------------
# AC4 — Each article includes headline and attachment_url from metadata
# ---------------------------------------------------------------------------


def test_ac4_results_have_headline():
    """Every result must have a non-empty headline field."""
    results = _call_search("vector search", k=3)
    assert len(results) >= 1, "Need at least one result"
    for r in results:
        assert "headline" in r, f"Result id={r.get('id')} missing 'headline'"
        assert isinstance(r["headline"], str), (
            f"headline must be a string for id={r.get('id')}"
        )


def test_ac4_results_have_attachment_url():
    """Every result must have an attachment_url field (may be null)."""
    results = _call_search("vector search", k=3)
    for r in results:
        assert "attachment_url" in r, (
            f"Result id={r.get('id')} missing 'attachment_url'"
        )


# ---------------------------------------------------------------------------
# AC5 — Each article includes up to N chunks with text and score, sorted desc
# ---------------------------------------------------------------------------


def test_ac5_results_have_chunks_array():
    """Every result must have a non-empty chunks array."""
    results = _call_search("vector search", k=3)
    assert len(results) >= 1, "Need at least one result"
    for r in results:
        assert "chunks" in r, (
            f"Result id={r.get('id')} missing 'chunks'. Keys: {list(r.keys())}"
        )
        assert isinstance(r["chunks"], list), (
            f"'chunks' must be a list for id={r.get('id')}"
        )
        assert len(r["chunks"]) >= 1, (
            f"'chunks' must have at least one element for id={r.get('id')}"
        )


def test_ac5_chunks_have_text_and_score():
    """Each chunk must have non-empty text and a numeric score."""
    results = _call_search("vector search embedding", k=3)
    for r in results:
        for i, c in enumerate(r.get("chunks", [])):
            assert "text" in c, f"chunks[{i}] missing 'text' for id={r.get('id')}"
            assert isinstance(c["text"], str) and c["text"].strip(), (
                f"chunks[{i}].text must be non-empty string for id={r.get('id')}"
            )
            assert "score" in c, f"chunks[{i}] missing 'score' for id={r.get('id')}"
            assert isinstance(c["score"], (int, float)), (
                f"chunks[{i}].score must be numeric for id={r.get('id')}"
            )


def test_ac5_chunks_sorted_by_score_descending():
    """Chunks within each article must be sorted by score descending."""
    results = _call_search("vector embedding similarity", k=5)
    for r in results:
        chunks = r.get("chunks", [])
        if len(chunks) < 2:
            continue
        scores = [c["score"] for c in chunks]
        for i in range(len(scores) - 1):
            assert scores[i] >= scores[i + 1], (
                f"Chunks not sorted by score descending for id={r.get('id')}: "
                f"scores={scores}"
            )


def test_ac5_chunks_count_does_not_exceed_default_n():
    """No article must have more chunks than the configured N."""
    with open(SEARCH_MODULE) as f:
        src = f.read()
    m = re.search(r"SEARCH_MAX_CHUNKS.*?(\d+)|MAX_CHUNKS.*?(\d+)", src)
    default_n = int(m.group(1) or m.group(2)) if m else 3

    results = _call_search("vector semantic search embedding cosine", k=10)
    for r in results:
        chunks = r.get("chunks", [])
        assert len(chunks) <= default_n, (
            f"Article id={r.get('id')} has {len(chunks)} chunks; "
            f"must not exceed N={default_n}"
        )


# ---------------------------------------------------------------------------
# AC6 — N is configurable via env var SEARCH_MAX_CHUNKS with documented default
# ---------------------------------------------------------------------------


def test_ac6_search_module_documents_default_n():
    """src/search/index.js must document or define a default for N."""
    with open(SEARCH_MODULE) as f:
        src = f.read()
    # Either a constant, an env var read with a default, or a comment
    assert re.search(
        r"SEARCH_MAX_CHUNKS|MAX_CHUNKS_PER_ARTICLE|maxChunksPerArticle",
        src
    ), (
        "src/search/index.js must define or reference SEARCH_MAX_CHUNKS / "
        "MAX_CHUNKS_PER_ARTICLE to document the configurable N"
    )


def test_ac6_env_var_limits_chunks_to_one():
    """Setting SEARCH_MAX_CHUNKS=1 must cap chunks per article at 1."""
    collection_path = os.path.join(REPO_ROOT, "collection.json")
    if not os.path.exists(collection_path):
        pytest.skip("collection.json not present")
    with open(collection_path) as f:
        rows = json.load(f)
    if not rows:
        pytest.skip("collection.json is empty")

    results = _call_search(
        "vector search embedding",
        k=10,
        env_extra={"SEARCH_MAX_CHUNKS": "1"},
    )
    for r in results:
        chunks = r.get("chunks", [])
        assert len(chunks) <= 1, (
            f"With SEARCH_MAX_CHUNKS=1, article id={r.get('id')} must have "
            f"at most 1 chunk, got {len(chunks)}"
        )


def test_ac6_env_var_allows_more_chunks():
    """Setting SEARCH_MAX_CHUNKS=5 must allow up to 5 chunks per article."""
    collection_path = os.path.join(REPO_ROOT, "collection.json")
    if not os.path.exists(collection_path):
        pytest.skip("collection.json not present")
    with open(collection_path) as f:
        rows = json.load(f)
    if not rows:
        pytest.skip("collection.json is empty")

    results = _call_search(
        "vector search embedding",
        k=10,
        env_extra={"SEARCH_MAX_CHUNKS": "5"},
    )
    for r in results:
        chunks = r.get("chunks", [])
        assert len(chunks) <= 5, (
            f"With SEARCH_MAX_CHUNKS=5, article id={r.get('id')} must have "
            f"at most 5 chunks, got {len(chunks)}"
        )


# ---------------------------------------------------------------------------
# AC7 — Multi-section document returns >1 chunk hit
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_DB, reason="Requires live server with Postgres backend")
def test_ac7_multi_section_document_returns_multiple_chunks(client):
    """An article with the query term in multiple sections returns >1 chunk."""
    repeated = "vector embedding semantic search " * 60
    separator = ". " * 10
    body = repeated + separator + repeated + separator + repeated
    r = client.post(
        "/articles",
        json={
            "headline": "Multi-Section AC7 Issue 103",
            "details": body,
            "attachment_url": "",
        },
    )
    assert r.status_code == 201
    article_id = r.json()["id"]

    try:
        resp = client.get("/search?q=vector+embedding+semantic&k=10")
        assert resp.status_code == 200
        results = resp.json().get("results", [])
        matching = [res for res in results if res.get("id") == article_id]
        assert len(matching) == 1, (
            f"Article {article_id} must appear exactly once"
        )
        chunks = matching[0].get("chunks", [])
        assert len(chunks) > 1, (
            f"Document with query terms in 3 sections must return >1 chunk, "
            f"got {len(chunks)}"
        )
    finally:
        client.delete(f"/articles/{article_id}")


# ---------------------------------------------------------------------------
# AC6 + integration — query parameter n caps chunks per article
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_DB, reason="Requires live server with Postgres backend")
def test_ac6_query_param_n_limits_chunks(client):
    """Query parameter n must cap the number of chunks per article in the response."""
    repeated = "vector embedding similarity cosine distance " * 60
    separator = ". " * 10
    body = repeated + separator + repeated + separator + repeated
    r = client.post(
        "/articles",
        json={
            "headline": "Query Param N Test Issue 103",
            "details": body,
            "attachment_url": "",
        },
    )
    assert r.status_code == 201
    article_id = r.json()["id"]

    try:
        resp = client.get("/search?q=vector+embedding+similarity&k=10&n=1")
        assert resp.status_code == 200
        results = resp.json().get("results", [])
        matching = [res for res in results if res.get("id") == article_id]
        if not matching:
            pytest.skip(f"Article {article_id} not in results")
        chunks = matching[0].get("chunks", [])
        assert len(chunks) <= 1, (
            f"With n=1, article must have at most 1 chunk, got {len(chunks)}"
        )
    finally:
        client.delete(f"/articles/{article_id}")
