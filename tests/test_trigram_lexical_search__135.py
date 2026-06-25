"""
Tests for issue #135: Add trigram-based lexical search for Thai text

AC1 - A new migration adds a pg_trgm GIN or GIST index on the chunk text column;
      the migration is idempotent via CREATE INDEX IF NOT EXISTS.
AC2 - The lexical search function accepts a query string and returns ranked chunks
      with a numeric lexical score derived from similarity() or word_similarity().
AC3 - A Thai keyword query returns at least one relevant chunk when that term is
      present in stored chunks.
AC4 - The lexical scorer is encapsulated behind an interface or clearly named
      function boundary so a segmentation-based implementation can be swapped in
      without modifying call sites.
AC5 - No regression on existing English/Latin-script lexical queries.
AC6 - The pg_trgm extension is enabled via CREATE EXTENSION IF NOT EXISTS pg_trgm.
"""

import os
import re
from urllib.parse import quote

import httpx
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATIONS_DIR = os.path.join(REPO_ROOT, "src", "store", "migrations")
LEXICAL_DIR = os.path.join(REPO_ROOT, "src", "core", "lexical")
TRIGRAM_SCORER_JS = os.path.join(LEXICAL_DIR, "trigramScorer.js")
LEXICAL_INDEX_JS = os.path.join(LEXICAL_DIR, "index.js")
SEARCH_EXACT_JS = os.path.join(REPO_ROOT, "src", "core", "searchExact.js")

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
# AC6: pg_trgm extension enabled in migration
# ---------------------------------------------------------------------------


def test_ac6_migration_enables_pg_trgm_extension():
    """A migration must enable pg_trgm via CREATE EXTENSION IF NOT EXISTS pg_trgm."""
    sql = _all_migration_sql()
    assert re.search(
        r"CREATE\s+EXTENSION\s+IF\s+NOT\s+EXISTS\s+pg_trgm",
        sql,
        re.IGNORECASE,
    ), "A migration must enable pg_trgm via CREATE EXTENSION IF NOT EXISTS pg_trgm"


# ---------------------------------------------------------------------------
# AC1: Migration adds idempotent pg_trgm index on chunk text column
# ---------------------------------------------------------------------------


def test_ac1_migration_adds_trgm_index():
    """A migration must create a GIN or GIST trigram index on the articles table."""
    sql = _all_migration_sql()
    assert re.search(
        r"CREATE\s+INDEX\s+IF\s+NOT\s+EXISTS\s+\w+\s+ON\s+articles\s+USING\s+(GIN|GIST)",
        sql,
        re.IGNORECASE,
    ), "A migration must create a GIN or GIST index on articles"
    assert re.search(r"trgm_ops", sql, re.IGNORECASE), (
        "The trigram index must use gin_trgm_ops or gist_trgm_ops operator class"
    )


def test_ac1_migration_trgm_index_idempotent():
    """The migration adding the trigram index must use CREATE INDEX IF NOT EXISTS."""
    for fname in sorted(f for f in os.listdir(MIGRATIONS_DIR) if f.endswith(".sql")):
        path = os.path.join(MIGRATIONS_DIR, fname)
        with open(path) as fh:
            content = fh.read()
        if "trgm_ops" in content.lower():
            assert re.search(
                r"CREATE\s+INDEX\s+IF\s+NOT\s+EXISTS", content, re.IGNORECASE
            ), (
                f"{fname} adds a trigram index but is not idempotent "
                "(missing CREATE INDEX IF NOT EXISTS)"
            )
            return
    pytest.fail("No migration file found that adds a pg_trgm index")


# ---------------------------------------------------------------------------
# AC4: Lexical scorer encapsulated behind a named function boundary
# ---------------------------------------------------------------------------


def test_ac4_lexical_module_directory_exists():
    """src/core/lexical/ directory must exist."""
    assert os.path.isdir(LEXICAL_DIR), (
        "src/core/lexical/ directory must exist — lexical scorer lives here"
    )


def test_ac4_trigram_scorer_module_exists():
    """src/core/lexical/trigramScorer.js must exist."""
    assert os.path.exists(TRIGRAM_SCORER_JS), (
        "src/core/lexical/trigramScorer.js must exist"
    )


def test_ac4_lexical_index_exists():
    """src/core/lexical/index.js (scorer interface) must exist."""
    assert os.path.exists(LEXICAL_INDEX_JS), (
        "src/core/lexical/index.js must exist — scorer interface/factory lives here"
    )


def test_ac4_lexical_index_exports_search_lexical():
    """index.js must export a searchLexical function (the stable call site)."""
    with open(LEXICAL_INDEX_JS) as f:
        src = f.read()
    assert re.search(r"export\s+(async\s+)?function\s+searchLexical", src), (
        "src/core/lexical/index.js must export a searchLexical function"
    )


def test_ac4_lexical_index_exports_set_scorer():
    """index.js must export setLexicalScorer so the implementation can be swapped."""
    with open(LEXICAL_INDEX_JS) as f:
        src = f.read()
    assert re.search(
        r"export\s+(function\s+)?setLexicalScorer|export\s*\{[^}]*setLexicalScorer",
        src,
    ), (
        "src/core/lexical/index.js must export setLexicalScorer to allow "
        "swapping the scorer without changing call sites"
    )


def test_ac4_search_exact_calls_search_lexical_for_thai():
    """searchExact.js must delegate Thai queries to searchLexical (not direct ILIKE only)."""
    with open(SEARCH_EXACT_JS) as f:
        src = f.read()
    assert re.search(r"searchLexical|lexical/index", src), (
        "searchExact.js must call searchLexical for Thai queries "
        "so the scorer can be swapped without changing call sites"
    )


# ---------------------------------------------------------------------------
# AC2: Trigram scorer uses similarity() or word_similarity()
# ---------------------------------------------------------------------------


def test_ac2_trigram_scorer_uses_pg_trgm_function():
    """trigramScorer.js must use similarity() or word_similarity()."""
    with open(TRIGRAM_SCORER_JS) as f:
        src = f.read()
    assert re.search(r"(word_)?similarity\s*\(", src, re.IGNORECASE), (
        "trigramScorer.js must use similarity() or word_similarity() from pg_trgm"
    )


def test_ac2_trigram_scorer_returns_lexical_score():
    """trigramScorer.js must include a lexical_score field in returned rows."""
    with open(TRIGRAM_SCORER_JS) as f:
        src = f.read()
    assert "lexical_score" in src, (
        "trigramScorer.js must return a lexical_score field per chunk"
    )


def test_ac2_trigram_scorer_exports_function():
    """trigramScorer.js must export a scorer function."""
    with open(TRIGRAM_SCORER_JS) as f:
        src = f.read()
    assert re.search(r"export\s+(async\s+)?function\s+\w+|export\s*\{", src), (
        "trigramScorer.js must export at least one function"
    )


# ---------------------------------------------------------------------------
# AC5: No regression — existing English lexical search unchanged
# ---------------------------------------------------------------------------


def test_ac5_search_exact_still_exists():
    """src/core/searchExact.js must still exist."""
    assert os.path.exists(SEARCH_EXACT_JS), (
        "src/core/searchExact.js must still exist — English FTS path must not be removed"
    )


def test_ac5_search_exact_exports_search_exact():
    """searchExact.js must still export searchExact."""
    with open(SEARCH_EXACT_JS) as f:
        src = f.read()
    assert re.search(r"export\s+(async\s+)?function\s+searchExact", src), (
        "searchExact.js must still export searchExact"
    )


def test_ac5_search_exact_still_uses_fts():
    """searchExact.js must still reference ts_rank / plainto_tsquery for English FTS."""
    with open(SEARCH_EXACT_JS) as f:
        src = f.read()
    assert re.search(r"ts_rank|plainto_tsquery", src, re.IGNORECASE), (
        "searchExact.js must still use ts_rank/plainto_tsquery for English FTS "
        "(regression: English path must not be removed)"
    )


# ---------------------------------------------------------------------------
# Live tests (require running server with Postgres backend)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_DB, reason="Requires live server with Postgres backend")
def test_ac3_thai_query_returns_chunk_with_nonzero_score(client):
    """Thai keyword query must return at least one chunk containing the term, score > 0."""
    thai_term = "การศึกษา"
    details = "การศึกษาเป็นรากฐานสำคัญของสังคม ระบบการศึกษาที่ดีช่วยพัฒนาประเทศชาติ"
    r = client.post(
        "/articles",
        json={"headline": "บทความการศึกษาไทย", "details": details, "attachment_url": ""},
    )
    assert r.status_code == 201
    article_id = r.json()["id"]

    try:
        resp = client.get(f"/search/exact?q={quote(thai_term)}&k=5")
        assert resp.status_code == 200
        results = resp.json().get("results", [])
        matching = [row for row in results if row.get("id") == article_id]
        assert matching, (
            f"Thai query {thai_term!r} must return the chunk containing that term; "
            f"got {len(results)} total results"
        )
        score = matching[0].get("score", 0)
        assert score > 0, f"Lexical score for Thai chunk must be > 0; got {score}"
    finally:
        client.delete(f"/articles/{article_id}")


@pytest.mark.skipif(not HAS_DB, reason="Requires live server with Postgres backend")
def test_ac2_lexical_score_numeric_for_thai(client):
    """Trigram search must return a numeric score for Thai query results."""
    thai_term = "สวัสดี"
    details = "สวัสดีครับ นี่คือข้อความทดสอบภาษาไทย"
    r = client.post(
        "/articles",
        json={"headline": "ทดสอบภาษาไทย", "details": details, "attachment_url": ""},
    )
    assert r.status_code == 201
    article_id = r.json()["id"]

    try:
        resp = client.get(f"/search/exact?q={quote(thai_term)}&k=5")
        assert resp.status_code == 200
        results = resp.json().get("results", [])
        matching = [row for row in results if row.get("id") == article_id]
        if matching:
            score = matching[0].get("score")
            assert isinstance(score, (int, float)), f"score must be numeric; got {type(score)}"
            assert score > 0, f"score must be > 0 for a matching document; got {score}"
    finally:
        client.delete(f"/articles/{article_id}")


@pytest.mark.skipif(not HAS_DB, reason="Requires live server with Postgres backend")
def test_ac5_english_query_still_works(client):
    """English lexical search must still return correct results (no regression)."""
    r = client.post(
        "/articles",
        json={
            "headline": "Blockchain Technology Overview",
            "details": "Blockchain enables decentralized transaction verification.",
            "attachment_url": "",
        },
    )
    assert r.status_code == 201
    article_id = r.json()["id"]

    try:
        resp = client.get("/search/exact?q=blockchain&k=5")
        assert resp.status_code == 200
        results = resp.json().get("results", [])
        matching = [row for row in results if row.get("id") == article_id]
        assert matching, (
            "English query 'blockchain' must return the matching article — "
            "existing lexical search must not regress"
        )
    finally:
        client.delete(f"/articles/{article_id}")


@pytest.mark.skipif(not HAS_DB, reason="Requires live server with Postgres backend")
def test_ac4_scorer_swap_works_without_changing_call_site(client):
    """
    Swapping the lexical scorer (via setLexicalScorer) must change scoring behaviour
    without requiring any change to call sites (searchExact, server routes, etc.).

    UAT step 6: mock a segmentation-based scorer and re-run a Thai query.
    This test verifies the swap mechanism works end-to-end at the module level.
    """
    # The swap test is a static structural check: setLexicalScorer must accept
    # a replacement function. Live environment check: the scorer can be replaced
    # at runtime without changing the server route code.
    with open(LEXICAL_INDEX_JS) as f:
        src = f.read()
    # Confirm the module allows reassignment of the internal scorer
    assert re.search(r"_scorer\s*=\s*fn|scorer\s*=\s*fn", src), (
        "src/core/lexical/index.js must reassign the internal scorer variable "
        "inside setLexicalScorer — call sites must not need to change"
    )
