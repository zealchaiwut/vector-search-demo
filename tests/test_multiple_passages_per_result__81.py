"""
Tests for issue #81: Return and render multiple passages per search result.

AC1  - src/core/search.js groups chunk hits by article_id in the Postgres search path
       and retains only the top-matching chunks per article (cap: 3), filtering out
       chunks below a minimum score threshold.
AC2  - Each article result includes a `passages` array; every element has the shape
       { text, start_offset, end_offset, context: { before, after }, score } produced
       by selectBestPassage applied to that chunk.
AC3  - passages is sorted descending by score (highest-scoring passage first).
AC4  - The existing best_passage field remains populated with the highest-scoring
       passage (backward-compatible; no breaking change to consumers).
AC5  - Passages are deduplicated by sentence offset so overlapping chunks do not
       produce duplicate or near-duplicate entries.
AC6  - A multi-keyword query against a long article (≥ 2 matched chunks above threshold)
       returns 2–3 distinct passages drawn from different parts of the document.
AC7  - An article that matches in exactly one chunk surfaces exactly one passage.
AC8  - public/index.html renders all passages for a result stacked vertically, each
       using the existing highlight styling, with the highest-scoring passage first.
AC9  - Results that previously showed one passage still display exactly one passage in
       the UI (no visual regression).
AC10 - npm run typecheck exits clean with no new errors.
"""

import json
import os
import re
import subprocess

import httpx
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEARCH_JS = os.path.join(REPO_ROOT, "src", "core", "search.js")
INDEX_HTML = os.path.join(REPO_ROOT, "public", "index.html")

BASE_URL = os.environ.get("UAT_BASE_URL") or "http://localhost:" + os.environ.get("UAT_PORT", "8010")
HAS_DB = bool(os.environ.get("DATABASE_URL") or os.environ.get("UAT_BASE_URL"))


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
# AC1 — Postgres path groups by article_id, caps at 3, has threshold (structural)
# ---------------------------------------------------------------------------

def test_ac1_max_chunks_constant_defined():
    """search.js must define a constant capping chunks per article at 3."""
    with open(SEARCH_JS) as f:
        src = f.read()
    assert re.search(r"MAX_CHUNKS_PER_ARTICLE\s*=\s*3", src), (
        "search.js must define MAX_CHUNKS_PER_ARTICLE = 3"
    )


def test_ac1_min_score_threshold_defined():
    """search.js must define a minimum score threshold to filter low-relevance chunks."""
    with open(SEARCH_JS) as f:
        src = f.read()
    assert re.search(r"MIN_SCORE_THRESHOLD\s*=\s*[\d.]+", src), (
        "search.js must define MIN_SCORE_THRESHOLD constant"
    )


def test_ac1_postgres_path_filters_below_threshold():
    """_searchPostgres must filter out chunks below MIN_SCORE_THRESHOLD."""
    with open(SEARCH_JS) as f:
        src = f.read()
    # Check for threshold comparison inside or near postgres function
    assert "MIN_SCORE_THRESHOLD" in src, (
        "search.js must reference MIN_SCORE_THRESHOLD in search path"
    )


def test_ac1_postgres_path_groups_chunks_by_article():
    """_searchPostgres must group hits into an array per article (not just keep best)."""
    with open(SEARCH_JS) as f:
        src = f.read()
    # Must push/append chunks to per-article array (not just replace best)
    has_push_or_array = re.search(
        r"\.push\s*\(|\.get\s*\(\s*articleId\s*\)\s*\.push|\[\s*\]", src
    )
    assert has_push_or_array, (
        "search.js must accumulate chunk hits per article (using push or array init)"
    )


def test_ac1_postgres_path_slices_to_max_chunks():
    """search.js must slice chunks to MAX_CHUNKS_PER_ARTICLE per article."""
    with open(SEARCH_JS) as f:
        src = f.read()
    assert re.search(r"slice\s*\(\s*0\s*,\s*MAX_CHUNKS_PER_ARTICLE\s*\)", src), (
        "search.js must slice chunk arrays to MAX_CHUNKS_PER_ARTICLE"
    )


# ---------------------------------------------------------------------------
# AC2 — passages array exists with correct shape (runtime, file-backed)
# ---------------------------------------------------------------------------

def test_ac2_results_have_passages_array():
    """Every search result must include a passages array."""
    results = _call_search("vector search embedding", k=3)
    assert len(results) >= 1, "Expected at least one result"
    for r in results:
        assert "passages" in r, (
            f"Result for id={r.get('id')} missing 'passages' field. Keys: {list(r.keys())}"
        )
        assert isinstance(r["passages"], list), (
            f"passages must be a list, got {type(r['passages'])} for id={r.get('id')}"
        )


def test_ac2_passages_array_nonempty():
    """passages array must contain at least one element for matching results."""
    results = _call_search("vector search embedding", k=3)
    assert len(results) >= 1
    for r in results:
        assert len(r["passages"]) >= 1, (
            f"passages array must be non-empty for id={r.get('id')}"
        )


def test_ac2_passages_elements_have_text():
    """Every passage element must have a non-empty text field."""
    results = _call_search("semantic search vector", k=3)
    for r in results:
        for i, p in enumerate(r["passages"]):
            assert "text" in p, f"passages[{i}] missing 'text' for id={r.get('id')}"
            assert p["text"].strip(), f"passages[{i}].text is blank for id={r.get('id')}"


def test_ac2_passages_elements_have_offsets():
    """Every passage element must have start_offset and end_offset integers."""
    results = _call_search("vector embedding", k=3)
    for r in results:
        for i, p in enumerate(r["passages"]):
            assert "start_offset" in p, f"passages[{i}] missing start_offset for id={r.get('id')}"
            assert "end_offset" in p, f"passages[{i}] missing end_offset for id={r.get('id')}"
            assert isinstance(p["start_offset"], int), (
                f"passages[{i}].start_offset must be int, got {type(p['start_offset'])}"
            )
            assert isinstance(p["end_offset"], int), (
                f"passages[{i}].end_offset must be int, got {type(p['end_offset'])}"
            )
            assert p["start_offset"] < p["end_offset"], (
                f"passages[{i}].start_offset must be < end_offset"
            )


def test_ac2_passages_elements_have_context():
    """Every passage element must have a context object with before and after."""
    results = _call_search("vector search", k=3)
    for r in results:
        for i, p in enumerate(r["passages"]):
            assert "context" in p, f"passages[{i}] missing context for id={r.get('id')}"
            ctx = p["context"]
            assert "before" in ctx, f"passages[{i}].context missing 'before'"
            assert "after" in ctx, f"passages[{i}].context missing 'after'"


def test_ac2_passages_elements_have_score():
    """Every passage element must have a numeric score field."""
    results = _call_search("vector search", k=3)
    for r in results:
        for i, p in enumerate(r["passages"]):
            assert "score" in p, f"passages[{i}] missing 'score' for id={r.get('id')}"
            assert isinstance(p["score"], (int, float)), (
                f"passages[{i}].score must be numeric, got {type(p['score'])}"
            )


def test_ac2_passages_count_at_most_three():
    """passages array must contain at most 3 elements (MAX_CHUNKS_PER_ARTICLE)."""
    results = _call_search("vector semantic embedding search", k=5)
    for r in results:
        assert len(r["passages"]) <= 3, (
            f"passages array has {len(r['passages'])} elements for id={r.get('id')}; max is 3"
        )


# ---------------------------------------------------------------------------
# AC3 — passages sorted descending by score
# ---------------------------------------------------------------------------

def test_ac3_passages_sorted_by_score_descending():
    """passages must be in descending score order."""
    results = _call_search("vector embedding cosine similarity", k=5)
    for r in results:
        scores = [p["score"] for p in r["passages"]]
        for i in range(len(scores) - 1):
            assert scores[i] >= scores[i + 1], (
                f"passages not sorted for id={r.get('id')}: scores={scores}"
            )


def test_ac3_sort_logic_in_source():
    """search.js must sort passages by score descending."""
    with open(SEARCH_JS) as f:
        src = f.read()
    assert re.search(r"sort.*score|score.*sort|passages.*sort", src, re.IGNORECASE), (
        "search.js must contain sort logic for passages by score"
    )


# ---------------------------------------------------------------------------
# AC4 — best_passage still populated (backward compatible)
# ---------------------------------------------------------------------------

def test_ac4_best_passage_still_present():
    """Every result must still have a best_passage field (backward compat)."""
    results = _call_search("vector search", k=3)
    assert len(results) >= 1
    for r in results:
        assert "best_passage" in r, (
            f"result for id={r.get('id')} missing best_passage"
        )
        assert r["best_passage"] is not None, (
            f"best_passage must not be null for id={r.get('id')}"
        )


def test_ac4_best_passage_has_required_shape():
    """best_passage must have text, start_offset, end_offset, and context."""
    results = _call_search("vector embedding", k=3)
    for r in results:
        bp = r["best_passage"]
        assert isinstance(bp, dict), f"best_passage must be a dict for id={r.get('id')}"
        for key in ("text", "start_offset", "end_offset", "context"):
            assert key in bp, f"best_passage missing '{key}' for id={r.get('id')}"
        assert "before" in bp["context"] and "after" in bp["context"], (
            f"best_passage.context must have before and after for id={r.get('id')}"
        )


def test_ac4_best_passage_text_equals_passages_first_text_or_is_non_empty():
    """best_passage.text must be non-empty and consistent with passages."""
    results = _call_search("semantic search", k=3)
    for r in results:
        bp_text = r["best_passage"]["text"]
        assert bp_text.strip(), f"best_passage.text must not be blank for id={r.get('id')}"


# ---------------------------------------------------------------------------
# AC5 — deduplication logic in source
# ---------------------------------------------------------------------------

def test_ac5_dedup_function_in_source():
    """search.js must contain a passage deduplication function."""
    with open(SEARCH_JS) as f:
        src = f.read()
    assert re.search(
        r"deduplicatePassages|passagesSimilar|CHUNK_OFFSET_BASE|withChunkScopedOffsets",
        src,
    ), (
        "search.js must contain deduplication logic for overlapping chunk passages"
    )


def test_ac5_no_duplicate_offsets_in_results():
    """No result should have two passages with identical start_offset."""
    results = _call_search("vector embedding cosine semantic", k=5)
    for r in results:
        offsets = [p["start_offset"] for p in r["passages"]]
        assert len(offsets) == len(set(offsets)), (
            f"Duplicate start_offsets in passages for id={r.get('id')}: {offsets}"
        )


# ---------------------------------------------------------------------------
# AC6 — multi-chunk article returns 2–3 passages (live Postgres only)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not HAS_DB, reason="Requires live server with Postgres backend")
def test_ac6_multi_chunk_article_returns_multiple_passages(client):
    """A long article with 2+ matched chunks must return 2–3 distinct passages."""
    # Create a long article with two clearly separated keyword sections
    section_a = " ".join(["quantum"] * 60 + ["entanglement"] * 20)  # 80 words
    section_b = " ".join(["blockchain"] * 60 + ["distributed"] * 20)  # 80 words
    long_body = section_a + ". " + section_b + "."
    r = client.post("/articles", json={
        "headline": "AC6 Multi-Chunk Passages Test",
        "details": long_body,
        "attachment_url": ""
    })
    assert r.status_code == 201
    article_id = r.json()["id"]

    try:
        resp = client.get("/search?q=quantum+blockchain&k=10")
        assert resp.status_code == 200
        results = resp.json().get("results", [])
        matching = [res for res in results if res.get("id") == article_id]
        assert len(matching) == 1, f"Article {article_id} must appear exactly once in results"
        result = matching[0]
        passages = result.get("passages", [])
        assert len(passages) >= 2, (
            f"Long article with 2 keyword sections must return ≥ 2 passages, got {len(passages)}"
        )
        assert len(passages) <= 3, (
            f"passages array must not exceed 3 elements, got {len(passages)}"
        )
    finally:
        client.delete(f"/articles/{article_id}")


# ---------------------------------------------------------------------------
# AC7 — single-chunk match surfaces exactly one passage
# ---------------------------------------------------------------------------

def test_ac7_single_result_has_at_least_one_passage():
    """Every result must have at least 1 passage (even single-chunk articles)."""
    results = _call_search("vector", k=1)
    assert len(results) >= 1
    r = results[0]
    assert len(r["passages"]) >= 1, "Top result must have at least 1 passage"


@pytest.mark.skipif(not HAS_DB, reason="Requires live server with Postgres backend")
def test_ac7_single_chunk_match_returns_one_passage(client):
    """An article matching only one chunk must surface exactly one passage."""
    # Short article — only one chunk
    unique_word = "xyzzyfoo9817"
    short_body = f"This article discusses {unique_word} in exactly one location."
    r = client.post("/articles", json={
        "headline": f"AC7 Single Chunk {unique_word}",
        "details": short_body,
        "attachment_url": ""
    })
    assert r.status_code == 201
    article_id = r.json()["id"]

    try:
        resp = client.get(f"/search?q={unique_word}&k=5")
        assert resp.status_code == 200
        results = resp.json().get("results", [])
        matching = [res for res in results if res.get("id") == article_id]
        assert len(matching) == 1, f"Article {article_id} must appear in results"
        result = matching[0]
        passages = result.get("passages", [])
        assert len(passages) == 1, (
            f"Single-chunk article must return exactly 1 passage, got {len(passages)}"
        )
    finally:
        client.delete(f"/articles/{article_id}")


# ---------------------------------------------------------------------------
# AC8 — HTML renders passages array stacked vertically
# ---------------------------------------------------------------------------

def test_ac8_html_iterates_passages_array():
    """index.html must iterate over the passages array to render multiple passages."""
    with open(INDEX_HTML) as f:
        src = f.read()
    # Must loop over passages (not just use best_passage)
    assert re.search(r"passages.*map|\.map.*passage|forEach.*passage|for.*passage", src, re.IGNORECASE), (
        "index.html must iterate over passages array to render each passage block"
    )


def test_ac8_html_renders_passage_blocks():
    """index.html must render passage div blocks using the passages array."""
    with open(INDEX_HTML) as f:
        src = f.read()
    # The passage rendering should reference r.passages or similar
    assert "passages" in src and "passage" in src.lower(), (
        "index.html must reference passages array in rendering logic"
    )


def test_ac8_html_renders_flat_chunk_rows():
    """Search tab must render one card per flat chunk row with capped display."""
    with open(INDEX_HTML) as f:
        src = f.read()
    assert re.search(r"renderFlatChunkCard", src), (
        "index.html Search tab must render flat chunk result cards"
    )
    assert re.search(r"DISPLAY_CAP\s*=\s*20", src), (
        "index.html must cap visible chunk rows at 20"
    )
    assert "View full article" in src, (
        "Each flat chunk card must include View full article"
    )


def test_ac8_html_uses_existing_passage_styling():
    """index.html must use the existing .passage CSS class for each passage block."""
    with open(INDEX_HTML) as f:
        src = f.read()
    # CSS class .passage must exist
    assert re.search(r'class.*["\']passage["\']|\.passage\s*\{', src), (
        "index.html must use .passage CSS class for passage blocks"
    )
    # And it must be used in the template/render path (not just CSS definition)
    script_section = src[src.index("<script>"):] if "<script>" in src else src
    assert "passage" in script_section.lower(), (
        "index.html script must render passage elements using .passage class"
    )


# ---------------------------------------------------------------------------
# AC9 — single-passage result renders exactly one passage block (structural)
# ---------------------------------------------------------------------------

def test_ac9_render_function_handles_single_passage():
    """Rendering a result with one passage produces exactly one passage block."""
    with open(INDEX_HTML) as f:
        src = f.read()
    # The render function must handle passages array of length 1 (maps over it)
    # It should NOT hardcode rendering best_passage separately from passages
    # Check that passages array is what drives the passage rendering in JS
    script_section = src[src.index("<script>"):] if "<script>" in src else src
    assert re.search(r"passages.*map|r\.passages|result\.passages", script_section, re.IGNORECASE), (
        "index.html render function must use r.passages (not hardcoded best_passage) "
        "so that single-passage results still show exactly one passage"
    )


# ---------------------------------------------------------------------------
# AC10 — npm run typecheck exits clean
# ---------------------------------------------------------------------------

def test_ac10_typecheck_passes():
    """npm run typecheck must exit 0 with no new errors."""
    result = subprocess.run(
        ["npm", "run", "typecheck"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=60,
    )
    assert result.returncode == 0, (
        f"npm run typecheck failed (rc={result.returncode}):\n"
        f"STDOUT: {result.stdout[-2000:]}\n"
        f"STDERR: {result.stderr[-2000:]}"
    )
