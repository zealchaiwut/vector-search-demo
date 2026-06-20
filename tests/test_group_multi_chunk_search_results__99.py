"""
Tests for issue #99: Group multi-chunk search results by parent document.

AC1  - Vector search runs over individual chunks, not collapsed per document
AC2  - Results are grouped by parent article (article_id / attachment_url)
AC3  - Articles are ranked by their best (highest) chunk score, descending
AC4  - Each article includes up to N matching chunks (N is configurable), ordered by score descending
AC5  - Each chunk object exposes at minimum: text and score
AC6  - Each article object exposes at minimum: headline, attachment_url, and a chunks array
AC7  - A Thai document that contains the query terms in several distinct passages returns
       more than one chunk under that article in the response
AC8  - Articles with only one matching chunk continue to work correctly (single-item chunks array)
AC9  - Changes are contained within src/search; no other modules are modified
AC10 - Existing search API contract is preserved (no breaking changes to callers beyond the
       enriched response shape)
"""

import json
import os
import re
import subprocess

import httpx
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEARCH_JS = os.path.join(REPO_ROOT, "src", "core", "search.js")

BASE_URL = (
    os.environ.get("UAT_BASE_URL")
    or "http://localhost:" + os.environ.get("UAT_PORT", "8010")
)
HAS_DB = bool(os.environ.get("DATABASE_URL") or os.environ.get("UAT_BASE_URL"))


def _run_node(script, timeout=60):
    result = subprocess.run(
        ["node", "--input-type=module"],
        input=script,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=timeout,
    )
    return result.stdout, result.stderr, result.returncode


def _call_search(query, k=5):
    script = f"""
import {{ searchDocuments }} from './src/core/search.js';
const results = await searchDocuments({json.dumps(query)}, {k});
process.stdout.write(JSON.stringify(results));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error (rc={rc}):\n{err}"
    return json.loads(out)


@pytest.fixture
def client():
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as c:
        yield c


# ---------------------------------------------------------------------------
# AC1 — Vector search runs over individual chunks
# ---------------------------------------------------------------------------


def test_ac1_collection_json_has_chunk_rows():
    """collection.json must contain chunk rows with ':N' suffixed ids."""
    collection_path = os.path.join(REPO_ROOT, "collection.json")
    if not os.path.exists(collection_path):
        pytest.skip("collection.json not present")
    with open(collection_path) as f:
        rows = json.load(f)
    chunk_rows = [r for r in rows if ":" in str(r.get("id", ""))]
    assert len(chunk_rows) > 0, (
        "collection.json must contain chunk rows with ':N' suffixed ids so "
        "search operates at chunk granularity"
    )


def test_ac1_search_scores_chunks_individually():
    """Search must run embedding lookup against all chunk rows, not article-level rows."""
    with open(SEARCH_JS) as f:
        src = f.read()
    # Must score all rows including multi-chunk ones
    assert re.search(r"id\.split\s*\(\s*['\"]:\s*['\"]\)", src) or \
           re.search(r"articleId.*split|split.*articleId", src), (
        "search.js must split chunk ids by ':' to derive article ids, "
        "indicating search runs at chunk granularity"
    )


# ---------------------------------------------------------------------------
# AC2 — Results grouped by parent article
# ---------------------------------------------------------------------------


def test_ac2_results_deduplicated_by_article():
    """Each article must appear at most once in search results."""
    results = _call_search("vector search embedding", k=10)
    ids = [r.get("id") for r in results]
    assert len(ids) == len(set(ids)), (
        f"Search results must not have duplicate article ids; got duplicates: "
        f"{[i for i in ids if ids.count(i) > 1]}"
    )


def test_ac2_result_ids_are_article_level():
    """Result ids must be article-level (no ':N' suffix)."""
    results = _call_search("vector search", k=5)
    for r in results:
        result_id = str(r.get("id", ""))
        assert ":" not in result_id, (
            f"Result id '{result_id}' looks like a chunk id (contains ':'); "
            "results must be grouped to article level"
        )


# ---------------------------------------------------------------------------
# AC3 — Articles ranked by best chunk score, descending
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


def test_ac3_article_score_is_best_chunk_score():
    """Article-level score must equal the best chunk score for that article."""
    results = _call_search("vector search", k=5)
    for r in results:
        chunks = r.get("chunks", [])
        if not chunks:
            continue
        best_chunk_score = max(c["score"] for c in chunks)
        article_score = r.get("score", 0)
        assert abs(article_score - best_chunk_score) < 1e-4, (
            f"Article score {article_score} must equal best chunk score {best_chunk_score} "
            f"for article id={r.get('id')}"
        )


# ---------------------------------------------------------------------------
# AC4 — Each article has up to N chunks (N configurable)
# ---------------------------------------------------------------------------


def test_ac4_max_chunks_per_article_constant_exists():
    """search.js must define MAX_CHUNKS_PER_ARTICLE to make N configurable."""
    with open(SEARCH_JS) as f:
        src = f.read()
    assert re.search(r"MAX_CHUNKS_PER_ARTICLE\s*=\s*\d+", src), (
        "search.js must define MAX_CHUNKS_PER_ARTICLE constant to make N configurable"
    )


def test_ac4_chunks_count_does_not_exceed_max():
    """No article must have more than MAX_CHUNKS_PER_ARTICLE chunks."""
    with open(SEARCH_JS) as f:
        src = f.read()
    m = re.search(r"MAX_CHUNKS_PER_ARTICLE\s*=\s*(\d+)", src)
    max_n = int(m.group(1)) if m else 3

    results = _call_search("vector semantic search embedding cosine", k=10)
    for r in results:
        chunks = r.get("chunks", [])
        assert len(chunks) <= max_n, (
            f"Article id={r.get('id')} has {len(chunks)} chunks; "
            f"must not exceed MAX_CHUNKS_PER_ARTICLE={max_n}"
        )


def test_ac4_chunks_ordered_by_score_descending():
    """Chunks within each article must be ordered by score descending."""
    results = _call_search("vector embedding similarity", k=5)
    for r in results:
        chunks = r.get("chunks", [])
        if len(chunks) < 2:
            continue
        scores = [c["score"] for c in chunks]
        for i in range(len(scores) - 1):
            assert scores[i] >= scores[i + 1], (
                f"Chunks not sorted by score descending for article id={r.get('id')}: "
                f"scores={scores}"
            )


# ---------------------------------------------------------------------------
# AC5 — Each chunk has text and score
# ---------------------------------------------------------------------------


def test_ac5_chunks_array_exists():
    """Every result must have a non-empty chunks array."""
    results = _call_search("vector search", k=3)
    assert len(results) >= 1, "Need at least one result"
    for r in results:
        assert "chunks" in r, (
            f"Result id={r.get('id')} missing 'chunks' field. Keys: {list(r.keys())}"
        )
        assert isinstance(r["chunks"], list), (
            f"'chunks' must be a list for id={r.get('id')}, got {type(r['chunks'])}"
        )
        assert len(r["chunks"]) >= 1, (
            f"'chunks' must have at least one element for id={r.get('id')}"
        )


def test_ac5_chunks_have_text_field():
    """Each chunk must have a non-empty 'text' field."""
    results = _call_search("vector search embedding", k=3)
    for r in results:
        for i, c in enumerate(r.get("chunks", [])):
            assert "text" in c, (
                f"chunks[{i}] missing 'text' for article id={r.get('id')}"
            )
            assert isinstance(c["text"], str) and c["text"].strip(), (
                f"chunks[{i}].text must be a non-empty string for id={r.get('id')}"
            )


def test_ac5_chunks_have_score_field():
    """Each chunk must have a numeric 'score' field."""
    results = _call_search("vector search embedding", k=3)
    for r in results:
        for i, c in enumerate(r.get("chunks", [])):
            assert "score" in c, (
                f"chunks[{i}] missing 'score' for article id={r.get('id')}"
            )
            assert isinstance(c["score"], (int, float)), (
                f"chunks[{i}].score must be numeric for id={r.get('id')}, "
                f"got {type(c['score'])}"
            )


def test_ac5_chunk_scores_are_positive():
    """Chunk scores must be positive (above zero threshold)."""
    results = _call_search("vector search", k=5)
    for r in results:
        for i, c in enumerate(r.get("chunks", [])):
            assert c["score"] > 0, (
                f"chunks[{i}].score must be > 0 for id={r.get('id')}, got {c['score']}"
            )


# ---------------------------------------------------------------------------
# AC6 — Each article exposes headline, attachment_url, and chunks
# ---------------------------------------------------------------------------


def test_ac6_results_have_headline():
    """Every result must have a headline field."""
    results = _call_search("vector search", k=3)
    assert len(results) >= 1
    for r in results:
        assert "headline" in r, f"Result id={r.get('id')} missing 'headline'"
        assert isinstance(r["headline"], str), (
            f"headline must be a string for id={r.get('id')}"
        )


def test_ac6_results_have_attachment_url():
    """Every result must have an attachment_url field (may be null)."""
    results = _call_search("vector search", k=3)
    for r in results:
        assert "attachment_url" in r, (
            f"Result id={r.get('id')} missing 'attachment_url'"
        )


def test_ac6_results_have_chunks_array():
    """Every result must have a chunks array (non-empty)."""
    results = _call_search("vector search", k=3)
    for r in results:
        assert "chunks" in r, f"Result id={r.get('id')} missing 'chunks'"
        assert isinstance(r["chunks"], list), (
            f"chunks must be list for id={r.get('id')}"
        )
        assert len(r["chunks"]) >= 1, (
            f"chunks must not be empty for id={r.get('id')}"
        )


# ---------------------------------------------------------------------------
# AC7 — Thai document with query terms in multiple sections returns >1 chunk
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_DB, reason="Requires live server with Postgres backend")
def test_ac7_thai_multi_section_document_returns_multiple_chunks(client):
    """A Thai document with the query term in multiple sections must return >1 chunk."""
    # Three clearly separated Thai sections mentioning the same keyword
    section_a = "การเรียนรู้ของเครื่อง " * 40  # machine learning repeated
    section_b = "." + " " * 20  # separator
    section_c = "การเรียนรู้ของเครื่อง " * 40  # same keyword again
    section_d = "." + " " * 20
    section_e = "การเรียนรู้ของเครื่อง " * 40  # third occurrence
    long_thai_body = section_a + section_b + section_c + section_d + section_e

    r = client.post(
        "/articles",
        json={
            "headline": "Thai Multi-Section AC7",
            "details": long_thai_body,
            "attachment_url": "",
        },
    )
    assert r.status_code == 201
    article_id = r.json()["id"]

    try:
        resp = client.get("/search?q=การเรียนรู้ของเครื่อง&k=10")
        assert resp.status_code == 200
        results = resp.json().get("results", [])
        matching = [res for res in results if res.get("id") == article_id]
        assert len(matching) == 1, (
            f"Thai article {article_id} must appear exactly once in results"
        )
        chunks = matching[0].get("chunks", [])
        assert len(chunks) > 1, (
            f"Thai document with query term in 3 sections must return >1 chunk, "
            f"got {len(chunks)}"
        )
    finally:
        client.delete(f"/articles/{article_id}")


# ---------------------------------------------------------------------------
# AC8 — Single-chunk articles work correctly (single-item chunks array)
# ---------------------------------------------------------------------------


def test_ac8_single_match_has_non_empty_chunks():
    """Every result, including single-match ones, must have at least one chunk."""
    results = _call_search("vector", k=1)
    assert len(results) >= 1
    r = results[0]
    chunks = r.get("chunks", [])
    assert len(chunks) >= 1, (
        f"Top result must have at least 1 chunk, got {len(chunks)}"
    )


@pytest.mark.skipif(not HAS_DB, reason="Requires live server with Postgres backend")
def test_ac8_single_passage_article_returns_one_chunk(client):
    """An article matching only one chunk must surface exactly one chunk entry."""
    unique_term = "xqz99unique7788term"
    short_body = f"This article contains {unique_term} in exactly one place."
    r = client.post(
        "/articles",
        json={
            "headline": f"Single Chunk AC8 {unique_term}",
            "details": short_body,
            "attachment_url": "",
        },
    )
    assert r.status_code == 201
    article_id = r.json()["id"]

    try:
        resp = client.get(f"/search?q={unique_term}&k=5")
        assert resp.status_code == 200
        results = resp.json().get("results", [])
        matching = [res for res in results if res.get("id") == article_id]
        assert len(matching) == 1, (
            f"Article {article_id} must appear in results"
        )
        chunks = matching[0].get("chunks", [])
        assert len(chunks) == 1, (
            f"Short single-passage article must return exactly 1 chunk, got {len(chunks)}"
        )
    finally:
        client.delete(f"/articles/{article_id}")


# ---------------------------------------------------------------------------
# AC9 — Changes are contained within src/search (src/core/search.js)
# ---------------------------------------------------------------------------


def test_ac9_search_js_exists():
    """src/core/search.js must exist as the search module."""
    assert os.path.exists(SEARCH_JS), (
        f"Search module must exist at {SEARCH_JS}"
    )


def test_ac9_chunks_field_built_in_search_js():
    """search.js must build the chunks array from chunk data."""
    with open(SEARCH_JS) as f:
        src = f.read()
    # Must map chunk data to { text, score } objects
    assert re.search(r"chunks\s*:", src), (
        "search.js must build a 'chunks' field in the returned result object"
    )
    assert re.search(r"text.*score|score.*text", src, re.IGNORECASE), (
        "search.js must map chunk data to objects with text and score"
    )


# ---------------------------------------------------------------------------
# AC10 — Existing search API contract preserved (backward compat)
# ---------------------------------------------------------------------------


def test_ac10_best_passage_still_present():
    """Results must still have best_passage (backward compat)."""
    results = _call_search("vector search", k=3)
    assert len(results) >= 1
    for r in results:
        assert "best_passage" in r, (
            f"Result id={r.get('id')} missing 'best_passage' — backward compat broken"
        )


def test_ac10_passages_still_present():
    """Results must still have passages array (backward compat)."""
    results = _call_search("vector search", k=3)
    assert len(results) >= 1
    for r in results:
        assert "passages" in r, (
            f"Result id={r.get('id')} missing 'passages' — backward compat broken"
        )
        assert isinstance(r["passages"], list), (
            f"passages must be list for id={r.get('id')}"
        )


def test_ac10_score_field_still_present():
    """Results must still have top-level score (backward compat)."""
    results = _call_search("vector search", k=3)
    for r in results:
        assert "score" in r, f"Result missing 'score' field"
        assert isinstance(r["score"], (int, float)), "score must be numeric"


def test_ac10_headline_and_details_still_present():
    """Results must still have headline and details fields (backward compat)."""
    results = _call_search("vector search", k=3)
    for r in results:
        assert "headline" in r, "Result missing 'headline'"
        assert "details" in r, "Result missing 'details'"
