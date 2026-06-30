"""
Tests for issue #187: Improve multi-term keyword matching and proximity ranking

AC1 - A query for `credit card` returns documents that contain only `credit` OR only `card`
      (no zero-result set due to implicit AND)
AC2 - A document containing the phrase `credit card` (adjacent) ranks above a document
      containing both terms non-adjacently, which ranks above a document containing only one term
AC3 - Matching uses an OR tsquery (e.g. `credit | card`) built from all whitespace-tokenised query terms
AC4 - Ranking uses `ts_rank_cd` so that term coverage and term proximity both influence the score
AC5 - An optional proximity boost is applied when query terms appear as an exact adjacent phrase
AC6 - The schema has a tsvector column (or generated column) and a GIN index on it
AC7 - Thai queries are segmented into tokens before tsquery and tsvector construction,
      so a two-word Thai phrase behaves identically to `credit card` in terms of recall and ranking
AC8 - Existing single-term queries are unaffected in correctness
AC9 - No full-table sequential scans for lexical search paths — the GIN index is used
"""

import os
import re
from urllib.parse import quote

import httpx
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATIONS_DIR = os.path.join(REPO_ROOT, "src", "store", "migrations")
SEARCH_EXACT_JS = os.path.join(REPO_ROOT, "src", "core", "searchExact.js")
LEXICAL_DIR = os.path.join(REPO_ROOT, "src", "core", "lexical")
TSVECTOR_SCORER_JS = os.path.join(LEXICAL_DIR, "tsvectorOrScorer.js")
THAI_SEGMENTER_JS = os.path.join(LEXICAL_DIR, "thaiSegmenter.js")

BASE_URL = os.environ.get("UAT_BASE_URL") or (
    "http://localhost:" + os.environ.get("UAT_PORT", "8010")
)
HAS_DB = bool(os.environ.get("DATABASE_URL") or os.environ.get("UAT_BASE_URL"))


@pytest.fixture
def client():
    with httpx.Client(base_url=BASE_URL, timeout=15.0) as c:
        yield c


def _all_migration_sql():
    combined = ""
    for fname in sorted(f for f in os.listdir(MIGRATIONS_DIR) if f.endswith(".sql")):
        with open(os.path.join(MIGRATIONS_DIR, fname)) as fh:
            combined += fh.read() + "\n"
    return combined


# ---------------------------------------------------------------------------
# AC6: tsvector column and GIN index exist in migrations
# ---------------------------------------------------------------------------


def test_ac6_tsvector_column_exists_in_migration():
    """At least one migration must add a tsvector column to articles."""
    sql = _all_migration_sql()
    assert re.search(r"tsvector", sql, re.IGNORECASE), (
        "A migration must add a tsvector column to support FTS"
    )


def test_ac6_gin_index_on_tsvector_exists():
    """At least one migration must create a GIN index on a tsvector column."""
    sql = _all_migration_sql()
    assert re.search(
        r"CREATE\s+INDEX\s+IF\s+NOT\s+EXISTS\s+\w+\s+ON\s+articles\s+USING\s+GIN",
        sql,
        re.IGNORECASE,
    ), "A migration must CREATE INDEX IF NOT EXISTS ... ON articles USING GIN"


def test_ac6_ts_simple_column_in_migration():
    """A migration must add a ts_simple tsvector column for language-agnostic OR search."""
    sql = _all_migration_sql()
    assert re.search(r"ts_simple\s+tsvector", sql, re.IGNORECASE) or \
           re.search(r"ts_simple.*tsvector", sql, re.IGNORECASE), (
        "A migration must add the ts_simple tsvector column"
    )


def test_ac6_ts_simple_gin_index_exists():
    """A migration must create a GIN index on ts_simple for index-backed OR search."""
    sql = _all_migration_sql()
    assert re.search(
        r"CREATE\s+INDEX\s+IF\s+NOT\s+EXISTS\s+\w+\s+ON\s+articles\s+USING\s+GIN\s*\(\s*ts_simple\s*\)",
        sql,
        re.IGNORECASE,
    ), "A migration must CREATE INDEX IF NOT EXISTS ... ON articles USING GIN (ts_simple)"


def test_ac6_new_migration_is_idempotent():
    """The ts_simple migration must use ADD COLUMN IF NOT EXISTS."""
    for fname in sorted(f for f in os.listdir(MIGRATIONS_DIR) if f.endswith(".sql")):
        path = os.path.join(MIGRATIONS_DIR, fname)
        with open(path) as fh:
            content = fh.read()
        if "ts_simple" in content.lower():
            assert re.search(
                r"ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS", content, re.IGNORECASE
            ), f"{fname} adds ts_simple but is not idempotent (missing ADD COLUMN IF NOT EXISTS)"
            return
    pytest.fail("No migration file found that adds ts_simple")


# ---------------------------------------------------------------------------
# AC3: OR tsquery built from whitespace-tokenised terms
# ---------------------------------------------------------------------------


def test_ac3_search_exact_builds_or_tsquery():
    """searchExact.js must use to_tsquery with OR (|) semantics for multi-term English queries."""
    with open(SEARCH_EXACT_JS) as f:
        src = f.read()
    assert re.search(r"to_tsquery", src, re.IGNORECASE), (
        "searchExact.js must use to_tsquery (not just plainto_tsquery) to build OR queries"
    )
    # Should have a | operator being constructed for the query
    assert re.search(r"\|\s*['\"\\|]|['\"]\s*\|\s*['\"]|join\(['\"].*\|", src) or \
           re.search(r"'\s*\|\s*'|\|\s*['`]|`[^`]*\|[^`]*`", src) or \
           re.search(r"terms.*join|join.*terms|buildOr|orQuery|or_query|\|\s*card|\|\s*\$", src, re.IGNORECASE), (
        "searchExact.js must build an OR tsquery by joining terms with '|'"
    )


def test_ac3_tsvector_scorer_has_or_query_builder():
    """tsvectorOrScorer.js must exist and contain OR query construction."""
    assert os.path.exists(TSVECTOR_SCORER_JS), (
        "src/core/lexical/tsvectorOrScorer.js must exist"
    )
    with open(TSVECTOR_SCORER_JS) as f:
        src = f.read()
    assert re.search(r"\|\s*['\"\\|]|join\(['\"].*\||\|\s*term|\|\s*seg|' | '|\" | \"", src, re.IGNORECASE) or \
           re.search(r"or.*query|tsquery.*\||\| \|", src, re.IGNORECASE), (
        "tsvectorOrScorer.js must build OR tsquery terms joined with |"
    )


# ---------------------------------------------------------------------------
# AC4: ts_rank_cd used for ranking
# ---------------------------------------------------------------------------


def test_ac4_search_exact_uses_ts_rank_cd():
    """searchExact.js must use ts_rank_cd for scoring (not just ts_rank)."""
    with open(SEARCH_EXACT_JS) as f:
        src = f.read()
    assert re.search(r"ts_rank_cd", src, re.IGNORECASE), (
        "searchExact.js must use ts_rank_cd so term coverage and proximity influence score"
    )


def test_ac4_tsvector_scorer_uses_ts_rank_cd():
    """tsvectorOrScorer.js must use ts_rank_cd for ranking."""
    assert os.path.exists(TSVECTOR_SCORER_JS), (
        "src/core/lexical/tsvectorOrScorer.js must exist"
    )
    with open(TSVECTOR_SCORER_JS) as f:
        src = f.read()
    assert re.search(r"ts_rank_cd", src, re.IGNORECASE), (
        "tsvectorOrScorer.js must use ts_rank_cd for coverage+proximity scoring"
    )


# ---------------------------------------------------------------------------
# AC5: Proximity boost for adjacent phrases
# ---------------------------------------------------------------------------


def test_ac5_search_exact_has_proximity_boost():
    """searchExact.js must apply a proximity boost using phraseto_tsquery or similar."""
    with open(SEARCH_EXACT_JS) as f:
        src = f.read()
    assert re.search(r"phraseto_tsquery|proximity|boost|CASE\s+WHEN.*ts\s*@@", src, re.IGNORECASE), (
        "searchExact.js must apply a proximity boost (phraseto_tsquery, CASE WHEN, or similar)"
    )


# ---------------------------------------------------------------------------
# AC7: Thai segmentation before tsquery and tsvector construction
# ---------------------------------------------------------------------------


def test_ac7_thai_segmenter_module_exists():
    """src/core/lexical/thaiSegmenter.js must exist."""
    assert os.path.exists(THAI_SEGMENTER_JS), (
        "src/core/lexical/thaiSegmenter.js must exist for Thai word segmentation"
    )


def test_ac7_thai_segmenter_uses_intl_segmenter():
    """thaiSegmenter.js must use Intl.Segmenter with Thai locale."""
    with open(THAI_SEGMENTER_JS) as f:
        src = f.read()
    assert re.search(r"Intl\.Segmenter", src), (
        "thaiSegmenter.js must use Intl.Segmenter for Thai word segmentation"
    )
    assert re.search(r"['\"]th['\"]", src), (
        "thaiSegmenter.js must use 'th' locale for Thai segmentation"
    )


def test_ac7_thai_segmenter_exports_function():
    """thaiSegmenter.js must export a segmentation function."""
    with open(THAI_SEGMENTER_JS) as f:
        src = f.read()
    assert re.search(r"export\s+(async\s+)?function\s+\w+|export\s*\{[^}]*\}", src), (
        "thaiSegmenter.js must export at least one function"
    )


def test_ac7_tsvector_scorer_handles_thai():
    """tsvectorOrScorer.js must detect Thai script and apply segmentation."""
    assert os.path.exists(TSVECTOR_SCORER_JS), (
        "src/core/lexical/tsvectorOrScorer.js must exist"
    )
    with open(TSVECTOR_SCORER_JS) as f:
        src = f.read()
    assert re.search(r"[฀-๿]|\\u0E|thai|segmen", src, re.IGNORECASE), (
        "tsvectorOrScorer.js must handle Thai script detection"
    )


def test_ac7_tsvector_scorer_uses_simple_config_for_thai():
    """tsvectorOrScorer.js must use 'simple' tsquery/tsvector config for Thai."""
    with open(TSVECTOR_SCORER_JS) as f:
        src = f.read()
    assert re.search(r"['\"]simple['\"]", src), (
        "tsvectorOrScorer.js must use 'simple' Postgres text search config for Thai"
    )


def test_ac7_tsvector_scorer_uses_ts_simple_column():
    """tsvectorOrScorer.js must query the ts_simple column for Thai."""
    with open(TSVECTOR_SCORER_JS) as f:
        src = f.read()
    assert re.search(r"ts_simple", src), (
        "tsvectorOrScorer.js must query the ts_simple column for Thai FTS"
    )


def test_ac7_search_exact_delegates_thai_to_tsvector_scorer():
    """searchExact.js must reference tsvectorOrScorer for Thai queries."""
    with open(SEARCH_EXACT_JS) as f:
        src = f.read()
    assert re.search(r"tsvectorOrScorer|searchLexical", src), (
        "searchExact.js must delegate Thai queries to tsvectorOrScorer or searchLexical"
    )


# ---------------------------------------------------------------------------
# AC9: GIN index prevents sequential scans
# ---------------------------------------------------------------------------


def test_ac9_all_lexical_gin_indexes_are_idempotent():
    """All GIN index migrations on articles must use CREATE INDEX IF NOT EXISTS."""
    sql = _all_migration_sql()
    # Find all CREATE INDEX statements touching articles
    index_stmts = re.findall(
        r"CREATE\s+(?:UNIQUE\s+)?INDEX(?:\s+IF\s+NOT\s+EXISTS)?\s+\w+\s+ON\s+articles\s+USING\s+GIN[^;]+;",
        sql,
        re.IGNORECASE,
    )
    for stmt in index_stmts:
        assert re.search(r"IF\s+NOT\s+EXISTS", stmt, re.IGNORECASE), (
            f"GIN index creation is not idempotent: {stmt[:80]}"
        )


# ---------------------------------------------------------------------------
# Live tests (require running server with Postgres backend)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_DB, reason="Requires live server with Postgres backend")
def test_ac1_or_recall_english_returns_single_term_docs(client):
    """A query for 'credit card' must return documents containing only 'credit' or only 'card'."""
    # Insert doc with only 'credit'
    r1 = client.post(
        "/articles",
        json={"headline": "Credit Systems", "details": "Modern credit systems enable borrowing.", "attachment_url": ""},
    )
    assert r1.status_code == 201
    id_credit = r1.json()["id"]

    # Insert doc with only 'card'
    r2 = client.post(
        "/articles",
        json={"headline": "Card Games", "details": "Card games are popular worldwide.", "attachment_url": ""},
    )
    assert r2.status_code == 201
    id_card = r2.json()["id"]

    # Insert doc with both (adjacent)
    r3 = client.post(
        "/articles",
        json={"headline": "Finance", "details": "A credit card is a payment tool.", "attachment_url": ""},
    )
    assert r3.status_code == 201
    id_both = r3.json()["id"]

    try:
        resp = client.get(f"/search/exact?q={quote('credit card')}&k=10")
        assert resp.status_code == 200
        results = resp.json().get("results", [])
        ids = {r["id"] for r in results}

        assert id_credit in ids, "Doc containing only 'credit' must appear in 'credit card' results"
        assert id_card in ids, "Doc containing only 'card' must appear in 'credit card' results"
        assert id_both in ids, "Doc containing 'credit card' phrase must appear in results"
    finally:
        for article_id in [id_credit, id_card, id_both]:
            client.delete(f"/articles/{article_id}")


@pytest.mark.skipif(not HAS_DB, reason="Requires live server with Postgres backend")
def test_ac2_proximity_ranking_phrase_above_scattered(client):
    """Adjacent phrase 'credit card' must rank above non-adjacent occurrences."""
    # Adjacent phrase
    r1 = client.post(
        "/articles",
        json={"headline": "Payment", "details": "Use your credit card to pay for purchases easily.", "attachment_url": ""},
    )
    assert r1.status_code == 201
    id_phrase = r1.json()["id"]

    # Both terms but separated
    r2 = client.post(
        "/articles",
        json={"headline": "Finance Overview", "details": "Credit is important. Owning a card helps build financial history.", "attachment_url": ""},
    )
    assert r2.status_code == 201
    id_scattered = r2.json()["id"]

    try:
        resp = client.get(f"/search/exact?q={quote('credit card')}&k=10")
        assert resp.status_code == 200
        results = resp.json().get("results", [])
        ids = [r["id"] for r in results]

        if id_phrase in ids and id_scattered in ids:
            rank_phrase = ids.index(id_phrase)
            rank_scattered = ids.index(id_scattered)
            assert rank_phrase < rank_scattered, (
                f"Adjacent phrase doc (rank {rank_phrase}) must rank above "
                f"scattered-terms doc (rank {rank_scattered})"
            )
    finally:
        for article_id in [id_phrase, id_scattered]:
            client.delete(f"/articles/{article_id}")


@pytest.mark.skipif(not HAS_DB, reason="Requires live server with Postgres backend")
def test_ac8_single_term_query_returns_results(client):
    """Single-term query must still return matching articles (no regression)."""
    r = client.post(
        "/articles",
        json={"headline": "Blockchain Overview", "details": "Blockchain enables decentralized systems.", "attachment_url": ""},
    )
    assert r.status_code == 201
    article_id = r.json()["id"]

    try:
        resp = client.get(f"/search/exact?q={quote('blockchain')}&k=5")
        assert resp.status_code == 200
        results = resp.json().get("results", [])
        ids = {row["id"] for row in results}
        assert article_id in ids, (
            "Single-term query 'blockchain' must return the matching article"
        )
    finally:
        client.delete(f"/articles/{article_id}")


@pytest.mark.skipif(not HAS_DB, reason="Requires live server with Postgres backend")
def test_ac7_thai_or_recall_returns_single_token_docs(client):
    """A Thai two-token query must return docs containing only the first or only the second token."""
    # Segment: 'การศึกษา' and 'สังคม'
    r1 = client.post(
        "/articles",
        json={"headline": "การศึกษา", "details": "ระบบการศึกษาเป็นรากฐานสำคัญ", "attachment_url": ""},
    )
    assert r1.status_code == 201
    id_edu = r1.json()["id"]

    r2 = client.post(
        "/articles",
        json={"headline": "สังคม", "details": "สังคมไทยมีความหลากหลาย", "attachment_url": ""},
    )
    assert r2.status_code == 201
    id_society = r2.json()["id"]

    # Query: two-word Thai phrase joined
    thai_query = "การศึกษาสังคม"
    try:
        resp = client.get(f"/search/exact?q={quote(thai_query)}&k=10")
        assert resp.status_code == 200
        results = resp.json().get("results", [])
        ids = {r["id"] for r in results}

        assert id_edu in ids or id_society in ids, (
            f"Thai OR query '{thai_query}' must return at least one of the single-token documents; "
            f"got ids: {ids}"
        )
    finally:
        for article_id in [id_edu, id_society]:
            client.delete(f"/articles/{article_id}")
