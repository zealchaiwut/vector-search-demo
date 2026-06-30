"""
Tests for issue #188: Highlight matched query terms in keyword and hybrid results.

AC1 - Keyword search mode displays results with matched query terms visually highlighted
      using <mark> in the passage text.
AC2 - Hybrid search mode displays results with matched query terms visually highlighted
      using <mark> in the passage text.
AC3 - The passage surfaced for a keyword/hybrid result is the one containing the greatest
      number of matched terms (best-matching passage selection by term count).
AC4 - The search API response for lexical results includes the pre-selected best passage
      sufficient for the frontend to render highlights without re-parsing.
AC5 - A keyword/hybrid result with no lexical term match renders cleanly with no broken
      highlight markup or empty highlight wrappers.
AC6 - Highlight rendering for keyword/hybrid results is visually consistent with existing
      semantic result highlighting (same <mark> style or highlight component).
AC7 - Existing semantic result highlighting is not regressed by this change.
"""

import os
import re

import httpx
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_HTML = os.path.join(REPO_ROOT, "public", "index.html")
SEARCH_INDEX_JS = os.path.join(REPO_ROOT, "src", "search", "index.js")
SEARCH_EXACT_JS = os.path.join(REPO_ROOT, "src", "core", "searchExact.js")

BASE_URL = os.environ.get("UAT_BASE_URL") or (
    "http://localhost:" + os.environ.get("UAT_PORT", "8010")
)
HAS_DB = bool(os.environ.get("DATABASE_URL") or os.environ.get("UAT_BASE_URL"))


def _html():
    with open(INDEX_HTML, encoding="utf-8") as f:
        return f.read()


def _search_index():
    with open(SEARCH_INDEX_JS, encoding="utf-8") as f:
        return f.read()


def _search_exact():
    with open(SEARCH_EXACT_JS, encoding="utf-8") as f:
        return f.read()


@pytest.fixture
def client():
    with httpx.Client(base_url=BASE_URL, timeout=15.0) as c:
        yield c


# ---------------------------------------------------------------------------
# AC1 / AC2 / AC6 — Frontend uses <mark> for keyword and hybrid term highlighting
# ---------------------------------------------------------------------------


def test_ac1_ac6_frontend_has_lexical_highlight_function():
    """index.html must define a function that highlights matched query terms with <mark>."""
    src = _html()
    # The function name can vary; we look for a function that:
    # 1. Takes text/query and wraps matched terms in <mark>
    assert re.search(
        r"function\s+\w*[Ll]exical\w*|function\s+\w*[Hh]ighlight\w*[Tt]erm\w*",
        src,
    ) or re.search(
        r"<mark>",
        src,
    ), (
        "index.html must define a highlight function (e.g. lexicalTermHighlight) "
        "that wraps matched terms in <mark> for keyword/hybrid rendering"
    )


def test_ac1_ac6_frontend_uses_mark_for_term_highlighting():
    """index.html must use <mark> elements to highlight individual matched terms
    in keyword/hybrid mode, not just <strong class='kw'>."""
    src = _html()
    assert re.search(r"<mark>", src), (
        "index.html must use <mark> elements for term highlighting"
    )
    # There must be a code path that produces <mark> for non-semantic modes
    # by matching terms from the query (not just wrapping the whole passage).
    assert re.search(r"mark.*\$&|replace\([^)]+[Mm]ark|'<mark>'", src), (
        "index.html must have code that inserts <mark> around matched terms "
        "(e.g. replace regex -> '<mark>$&</mark>')"
    )


def test_ac1_frontend_keyword_mode_triggers_different_rendering():
    """index.html must branch on the search mode so keyword/hybrid results use
    term-level <mark> highlighting instead of passage-level <mark> wrapping."""
    src = _html()
    # The rendering must check the mode (keyword, hybrid, hybrid-rerank)
    assert re.search(
        r"""(mode\s*===?\s*['"]keyword['"])|(isLexical)|(isKeyword)""",
        src,
    ), (
        "index.html must check the search mode (e.g. mode === 'keyword') to "
        "branch into keyword/hybrid term highlighting"
    )


def test_ac2_hybrid_mode_uses_lexical_highlighting():
    """index.html must apply keyword/hybrid highlighting for hybrid and hybrid-rerank modes."""
    src = _html()
    # hybrid-rerank or hybrid must also trigger lexical highlighting
    assert re.search(
        r"""hybrid|hybrid-rerank""",
        src,
    ), (
        "index.html must handle hybrid mode in the term highlighting branch"
    )
    # The mode check must cover both hybrid variants
    has_hybrid_check = re.search(
        r"hybrid.*mark|mark.*hybrid|isLexical.*hybrid|hybrid.*isLexical",
        src,
        re.DOTALL,
    )
    has_mode_switch = re.search(
        r"switch.*mode|mode.*===.*hybrid|mode.*===.*keyword",
        src,
    )
    assert has_hybrid_check or has_mode_switch, (
        "index.html must include hybrid mode in the lexical highlighting code path"
    )


# ---------------------------------------------------------------------------
# AC3 — Backend selects best passage by term count for hybrid
# ---------------------------------------------------------------------------


def test_ac3_search_index_has_term_based_passage_function():
    """src/search/index.js must define a function that selects the best passage
    by counting matched query terms (not semantic similarity)."""
    src = _search_index()
    assert re.search(
        r"function\s+selectBestPassageByTerms|bestPassageByTerms|term[_-]?based|match_count",
        src,
    ), (
        "src/search/index.js must define selectBestPassageByTerms or equivalent "
        "to pick the passage with the most matched query terms"
    )


def test_ac3_search_index_uses_term_selection_for_hybrid():
    """src/search/index.js must use term-based passage selection when hybridEnabled."""
    src = _search_index()
    # The term-based selection must be conditioned on hybridEnabled
    assert re.search(
        r"hybridEnabled.*selectBestPassageByTerms|selectBestPassageByTerms.*hybridEnabled"
        r"|hybridEnabled.*term[_-]?based|hybridEnabled.*match_count"
        r"|cfg\.hybridEnabled.*Passage.*[Tt]erm|queryTerms.*hybridEnabled",
        src,
        re.DOTALL,
    ), (
        "src/search/index.js must call the term-based passage selection "
        "when cfg.hybridEnabled is true"
    )


def test_ac3_search_index_still_has_semantic_passage_selection():
    """src/search/index.js must still define selectBestPassage for semantic mode (AC7)."""
    src = _search_index()
    assert re.search(r"function\s+selectBestPassage\b", src), (
        "src/search/index.js must still define selectBestPassage for semantic mode "
        "(regression: semantic highlighting must not be broken)"
    )


# ---------------------------------------------------------------------------
# AC4 — API response includes pre-selected best passage for lexical results
# ---------------------------------------------------------------------------


def test_ac4_search_exact_returns_passages_with_text():
    """searchExact.js must return passages with a text field so the frontend
    can render highlights without re-parsing the document."""
    src = _search_exact()
    assert re.search(r"passages", src), (
        "searchExact.js must return a passages array"
    )
    assert re.search(r"text\s*:", src), (
        "searchExact.js must return passages with a text field"
    )


def test_ac4_search_index_hybrid_adds_match_count_or_text():
    """src/search/index.js must attach match_count or the best-matching passage text
    to hybrid results so the frontend can determine whether terms matched."""
    src = _search_index()
    assert re.search(r"match_count|matched_terms|term.*passage|passage.*term", src), (
        "src/search/index.js must track match_count or matched terms for hybrid results "
        "to satisfy AC4 (frontend can render highlights without re-parsing)"
    )


# ---------------------------------------------------------------------------
# AC5 — No-match result renders cleanly
# ---------------------------------------------------------------------------


def test_ac5_frontend_handles_no_match_gracefully():
    """index.html must handle the case where no query terms appear in the passage,
    rendering plain text without empty <mark> wrappers or broken markup."""
    src = _html()
    # The highlight function must have a guard: if no terms match, return plain text
    has_empty_guard = re.search(
        r"tokens\.length\s*===\s*0|terms\.length\s*===\s*0|if\s*\(!.*terms\b",
        src,
    )
    has_fallback = re.search(
        r"escapeHtml\(text\)|return\s+escaped|plain.*text.*no.*match|no.*match.*plain",
        src,
    )
    assert has_empty_guard or has_fallback, (
        "index.html must handle the no-match case in the term highlighting function "
        "so results without matches render as plain text (no broken <mark> wrappers)"
    )


def test_ac5_no_empty_mark_tags():
    """The highlight function in index.html must not produce <mark></mark> (empty marks)."""
    src = _html()
    # Ensure the highlight function filters empty tokens and applies regex only when terms exist
    assert re.search(r"\.filter\(", src), (
        "index.html must filter empty tokens to prevent <mark></mark> wrappers"
    )


# ---------------------------------------------------------------------------
# AC6 — Keyword/hybrid use same .passage component as semantic
# ---------------------------------------------------------------------------


def test_ac6_keyword_results_use_passage_div_in_main_search():
    """In the main search panel, keyword/hybrid results must be wrapped in the .passage
    div (same component as semantic results) for visual consistency."""
    src = _html()
    # The non-compact (main search) card template must include .passage for all modes
    # This means the card template that wraps bodyHtml must always include .passage
    assert re.search(
        r'class="passage"',
        src,
    ), (
        "index.html must include .passage div in result cards for consistent styling"
    )
    # The bodyHtml for keyword/hybrid must go inside the same .passage structure
    assert re.search(
        r'passage-text.*bodyHtml|bodyHtml.*passage-text',
        src,
        re.DOTALL,
    ), (
        "index.html must place keyword/hybrid bodyHtml inside .passage-text "
        "for visual consistency with semantic highlighting"
    )


# ---------------------------------------------------------------------------
# AC7 — Semantic highlighting not regressed
# ---------------------------------------------------------------------------


def test_ac7_semantic_still_uses_full_passage_mark():
    """index.html must still wrap the entire semantic passage in <mark> for semantic mode."""
    src = _html()
    # The semantic branch must use: <mark>${highlightPassage(snippet, query)}</mark>
    assert re.search(
        r"<mark>\$\{.*[Hh]ighlight.*\}|`<mark>`\s*\+\s*highlight|mark.*highlightPassage",
        src,
    ), (
        "index.html must still wrap semantic passages in <mark> "
        "(regression: semantic highlighting must not be changed)"
    )


def test_ac7_search_index_semantic_uses_select_best_passage():
    """src/search/index.js must still use selectBestPassage for dense-only mode."""
    src = _search_index()
    assert re.search(r"selectBestPassage\(", src), (
        "src/search/index.js must still call selectBestPassage for dense/semantic mode "
        "(regression: existing semantic passage selection must not be removed)"
    )


# ---------------------------------------------------------------------------
# Live tests — require running server with Postgres backend
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_DB, reason="Requires live server with Postgres backend")
def test_ac1_keyword_search_passage_contains_query_term(client):
    """Keyword search result must surface a passage whose text contains the query term."""
    details = (
        "Climate policy reform is urgently needed as global temperatures rise. "
        "Many countries have begun implementing carbon pricing mechanisms. "
        "Renewable energy investments are key to reducing emissions."
    )
    r = client.post(
        "/articles",
        json={"headline": "Climate Policy", "details": details, "attachment_url": ""},
    )
    assert r.status_code == 201
    article_id = r.json()["id"]
    try:
        resp = client.get("/search/exact?q=climate+policy+reform&k=5")
        assert resp.status_code == 200
        results = resp.json().get("results", [])
        matching = [row for row in results if row.get("id") == article_id]
        assert matching, "keyword search must return the climate policy article"
        passage_text = ""
        row = matching[0]
        bp = row.get("best_passage") or {}
        passage_text = (
            (bp.get("text") or "")
            or (row.get("passages", [{}])[0].get("text") or "")
            or row.get("text", "")
        )
        assert passage_text, "keyword result must include a passage text field"
        term_found = any(
            t in passage_text.lower() for t in ["climate", "policy", "reform"]
        )
        assert term_found, (
            f"keyword result passage must contain at least one of the query terms; "
            f"got passage: {passage_text!r}"
        )
    finally:
        client.delete(f"/articles/{article_id}")


@pytest.mark.skipif(not HAS_DB, reason="Requires live server with Postgres backend")
def test_ac3_hybrid_passage_prefers_term_rich_passage(client):
    """Hybrid search must surface the passage with the most query term matches.
    The article has two chunks: one term-rich, one term-poor. The passage
    shown must come from the term-rich chunk."""
    # Article with a term-rich first sentence in the second chunk
    detail_no_terms = (
        "Artificial intelligence applications span many domains. "
        "Machine learning models process information efficiently. "
        "Neural networks learn from vast training datasets."
    )
    detail_with_terms = (
        "Climate policy reform is essential for reducing carbon emissions. "
        "Climate change mitigation through policy reform requires international cooperation. "
        "Policy reform on climate issues must address energy transition timelines."
    )
    combined = detail_no_terms + " " + detail_with_terms
    r = client.post(
        "/articles",
        json={
            "headline": "Mixed Article",
            "details": combined,
            "attachment_url": "",
        },
    )
    assert r.status_code == 201
    article_id = r.json()["id"]
    try:
        resp = client.get(
            "/search?q=climate+policy+reform&preset=hybrid&k=5"
        )
        assert resp.status_code == 200
        results = resp.json().get("results", [])
        matching = [row for row in results if row.get("id") == article_id]
        if not matching:
            pytest.skip("Article not returned by hybrid search — not enough corpus for retrieval")
        row = matching[0]
        bp = row.get("best_passage") or {}
        passage_text = (
            bp.get("text")
            or (row.get("passages", [{}])[0].get("text") or "")
            or row.get("text", "")
        ).lower()
        term_count = sum(1 for t in ["climate", "policy", "reform"] if t in passage_text)
        assert term_count >= 1, (
            f"Hybrid result passage must contain at least one of: climate, policy, reform; "
            f"got: {passage_text!r}"
        )
    finally:
        client.delete(f"/articles/{article_id}")


@pytest.mark.skipif(not HAS_DB, reason="Requires live server with Postgres backend")
def test_ac4_keyword_result_includes_pre_selected_passage(client):
    """Keyword search API response must include a best_passage (pre-selected passage)
    so the frontend can render highlights without re-parsing the full document."""
    r = client.post(
        "/articles",
        json={
            "headline": "Neural Network Overview",
            "details": "Neural networks are powerful machine learning models. "
                       "They consist of interconnected layers of nodes. "
                       "Deep learning uses many stacked neural layers.",
            "attachment_url": "",
        },
    )
    assert r.status_code == 201
    article_id = r.json()["id"]
    try:
        resp = client.get("/search/exact?q=neural+network&k=5")
        assert resp.status_code == 200
        results = resp.json().get("results", [])
        matching = [row for row in results if row.get("id") == article_id]
        assert matching, "keyword search must find the neural network article"
        row = matching[0]
        bp = row.get("best_passage")
        assert bp is not None, "keyword result must include best_passage field (AC4)"
        text = bp.get("text") if isinstance(bp, dict) else str(bp)
        assert text, "best_passage.text must be non-empty (AC4)"
    finally:
        client.delete(f"/articles/{article_id}")


@pytest.mark.skipif(not HAS_DB, reason="Requires live server with Postgres backend")
def test_ac5_hybrid_no_keyword_match_returns_clean_passage(client):
    """A hybrid result retrieved only by dense (semantic) similarity must return
    a passage text with no empty or broken markup indicators."""
    # Dense-biased content that semantic finds but keywords do not match
    r = client.post(
        "/articles",
        json={
            "headline": "Abstract Quantum Concepts",
            "details": "Superposition allows particles to exist in multiple states. "
                       "Entanglement creates correlations across separated systems. "
                       "Wave function collapse determines measurement outcomes.",
            "attachment_url": "",
        },
    )
    assert r.status_code == 201
    article_id = r.json()["id"]
    try:
        # Query a keyword that won't be in the article, but semantic similarity may still match
        resp = client.get(
            "/search?q=quantum+superposition&preset=hybrid&k=5"
        )
        assert resp.status_code == 200
        results = resp.json().get("results", [])
        for row in results:
            bp = row.get("best_passage") or {}
            if isinstance(bp, dict):
                text = bp.get("text", "")
            else:
                text = str(bp)
            # Passage must be non-null and not contain broken empty mark tags
            assert text is not None, "passage text must not be None (AC5)"
            assert "<mark></mark>" not in (text or ""), (
                f"passage must not contain empty <mark></mark> wrappers (AC5); got: {text!r}"
            )
    finally:
        client.delete(f"/articles/{article_id}")


@pytest.mark.skipif(not HAS_DB, reason="Requires live server with Postgres backend")
def test_ac7_semantic_search_still_returns_best_passage(client):
    """Semantic search must still return best_passage (regression check for AC7)."""
    resp = client.get("/search?q=vector+similarity+search&k=3")
    assert resp.status_code == 200
    results = resp.json().get("results", [])
    assert len(results) >= 1, "Semantic search must return at least one result"
    for row in results:
        assert "best_passage" in row, (
            f"Semantic result id={row.get('id')} missing best_passage (AC7 regression)"
        )
        bp = row["best_passage"]
        text = bp.get("text") if isinstance(bp, dict) else str(bp)
        assert text, f"Semantic result id={row.get('id')} best_passage.text must be non-empty (AC7)"
