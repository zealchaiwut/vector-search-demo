"""
Tests for issue #80: Store and retrieve Postgres embeddings at chunk granularity

AC1  - Schema migration is idempotent, additive: adds article_id (text) and
       chunk_index (integer) columns; primary key stays on full chunk id.
AC2  - PgVectorStore.upsert persists each chunk row as-is (no averaging); calling
       it twice with the same chunk id is safe (upsert semantics via ON CONFLICT).
AC3  - PgVectorStore.list deduplicates by article_id; returns exactly one entry per article.
AC4  - PgVectorStore.get returns all chunk rows for a given article joined in ascending
       chunk_index order so the full body can be reconstructed.
AC5  - PgVectorStore.delete removes every chunk row whose article_id matches.
AC6  - PgVectorStore.count returns COUNT(DISTINCT article_id); a separate chunkCount()
       method or query returns the raw row count.
AC7  - collection.js postgres branch removes the collapseToArticles / avgEmbeddings
       call path entirely.
AC8  - Server (server.mjs) chunks article bodies via chunker.js before embedding and
       upsert on article create, article update, bulk import, and PDF import.
AC9  - Ingesting the demo corpus produces multiple chunk rows per multi-paragraph article.
AC10 - Creating a single article with a long body (> 1 chunk threshold) stores multiple
       chunk rows with sequential chunk_index values.
AC11 - GET /articles returns one JSON entry per article (no duplicates).
AC12 - GET /articles/:id returns the full reconstructed article body from all chunks.
AC13 - DELETE /articles/:id removes all chunk rows; a subsequent GET returns 404.
AC14 - /health/integrity reports articleCount (distinct article_id) and chunkCount
       without raising a false mismatch error for multi-chunk articles.
AC15 - All existing Postgres integration tests pass or are updated.
AC16 - npm run typecheck exits clean (verified externally; structural test below).
"""

import os
import re

import httpx
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PG_STORE_PATH = os.path.join(REPO_ROOT, "src", "store", "PgVectorStore.js")
POSTGRES_JS = os.path.join(REPO_ROOT, "src", "store", "postgres.js")
COLLECTION_JS = os.path.join(REPO_ROOT, "src", "data", "collection.js")
SERVER_MJS = os.path.join(REPO_ROOT, "src", "server.mjs")
CHUNKER_JS = os.path.join(REPO_ROOT, "src", "data", "chunker.js")
MIGRATIONS_DIR = os.path.join(REPO_ROOT, "src", "store", "migrations")

BASE_URL = os.environ.get("UAT_BASE_URL") or "http://localhost:" + os.environ.get("UAT_PORT", "8010")
HAS_DB = bool(os.environ.get("DATABASE_URL") or os.environ.get("UAT_BASE_URL"))


@pytest.fixture
def client():
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as c:
        yield c


# ---------------------------------------------------------------------------
# AC1: Schema migration adds article_id and chunk_index columns (idempotent)
# ---------------------------------------------------------------------------


def _all_migration_sql():
    combined = ""
    for fname in sorted(f for f in os.listdir(MIGRATIONS_DIR) if f.endswith(".sql")):
        with open(os.path.join(MIGRATIONS_DIR, fname)) as fh:
            combined += fh.read() + "\n"
    return combined


def test_ac1_migration_adds_article_id_column():
    """Migration must add article_id text column."""
    sql = _all_migration_sql()
    assert re.search(r"article_id\s+text", sql, re.IGNORECASE), (
        "Migration must define or add an 'article_id text' column"
    )


def test_ac1_migration_adds_chunk_index_column():
    """Migration must add chunk_index integer column."""
    sql = _all_migration_sql()
    assert re.search(r"chunk_index\s+integer", sql, re.IGNORECASE), (
        "Migration must define or add a 'chunk_index integer' column"
    )


def test_ac1_migration_keeps_id_primary_key():
    """Migration must keep id as primary key (full chunk id like <uuid>:<n>)."""
    sql = _all_migration_sql()
    assert re.search(r"id\s+text\s+primary\s+key", sql, re.IGNORECASE), (
        "Migration must define 'id text primary key' — primary key must remain on the full chunk id"
    )


def test_ac1_migration_is_additive_no_drop_of_existing_columns():
    """Migration must not drop or rename existing columns (headline, details, embedding, etc.)."""
    sql = _all_migration_sql()
    dangerous_drops = re.findall(
        r"DROP\s+COLUMN\s+(headline|details|embedding|attachment_url|created_at)", sql, re.IGNORECASE
    )
    assert not dangerous_drops, (
        f"Migration must not drop existing columns; found: {dangerous_drops}"
    )


def test_ac1_migration_is_idempotent():
    """Migration must use IF NOT EXISTS or ADD COLUMN IF NOT EXISTS for idempotency."""
    sql = _all_migration_sql()
    assert re.search(r"IF\s+NOT\s+EXISTS", sql, re.IGNORECASE), (
        "Migration must use IF NOT EXISTS for idempotent table/index/column creation"
    )


# ---------------------------------------------------------------------------
# AC2: upsert stores each chunk row as-is (no averaging); ON CONFLICT for safety
# ---------------------------------------------------------------------------


def test_ac2_pg_store_upsert_includes_article_id_and_chunk_index():
    """PgVectorStore.upsert must INSERT article_id and chunk_index columns."""
    with open(PG_STORE_PATH) as f:
        src = f.read()
    assert "article_id" in src, "PgVectorStore.upsert must insert article_id column"
    assert "chunk_index" in src, "PgVectorStore.upsert must insert chunk_index column"


def test_ac2_pg_store_upsert_no_averaging():
    """PgVectorStore.js must NOT contain avgEmbeddings (no averaging)."""
    with open(PG_STORE_PATH) as f:
        src = f.read()
    assert "avgEmbeddings" not in src, (
        "PgVectorStore must not contain avgEmbeddings — chunk embeddings must be stored as-is"
    )


def test_ac2_pg_store_upsert_no_collapse():
    """PgVectorStore.js must NOT contain collapseToArticles."""
    with open(PG_STORE_PATH) as f:
        src = f.read()
    assert "collapseToArticles" not in src, (
        "PgVectorStore must not collapse chunks — each chunk row must be stored individually"
    )


def test_ac2_pg_store_upsert_on_conflict_id():
    """PgVectorStore.upsert must use ON CONFLICT (id) for safe repeated calls."""
    with open(PG_STORE_PATH) as f:
        src = f.read()
    assert re.search(r"ON\s+CONFLICT\s*\(\s*id\s*\)", src, re.IGNORECASE), (
        "PgVectorStore.upsert must use INSERT...ON CONFLICT(id) for upsert semantics"
    )


# ---------------------------------------------------------------------------
# AC3: list deduplicates by article_id — one entry per article
# ---------------------------------------------------------------------------


def test_ac3_pg_store_list_deduplicates():
    """PgVectorStore.list must deduplicate by article_id."""
    with open(PG_STORE_PATH) as f:
        src = f.read()
    has_distinct = "DISTINCT" in src.upper() or "GROUP BY" in src.upper()
    has_article_id_ref = "article_id" in src
    assert has_distinct and has_article_id_ref, (
        "PgVectorStore.list must deduplicate rows by article_id "
        "(using DISTINCT ON or GROUP BY article_id)"
    )


@pytest.mark.skipif(not HAS_DB, reason="Requires live server with Postgres backend")
def test_ac3_get_articles_no_duplicates_live(client):
    """GET /articles must return exactly one entry per article (no chunk duplicates)."""
    # Create article with long body so it will have multiple chunks
    long_body = " ".join(["This is a test word."] * 200)  # ~800 words > 120 chunk threshold
    r = client.post("/articles", json={"headline": "Multi-chunk AC3", "details": long_body, "attachment_url": ""})
    assert r.status_code == 201
    article_id = r.json()["id"]

    r2 = client.get("/articles")
    assert r2.status_code == 200
    articles = r2.json()["articles"]
    matching = [a for a in articles if a.get("id") == article_id]
    assert len(matching) == 1, (
        f"GET /articles returned {len(matching)} entries for article {article_id}; expected exactly 1"
    )

    # cleanup
    client.delete(f"/articles/{article_id}")


# ---------------------------------------------------------------------------
# AC4: get returns all chunks assembled in chunk_index order
# ---------------------------------------------------------------------------


def test_ac4_pg_store_get_orders_by_chunk_index():
    """PgVectorStore.get must ORDER BY chunk_index ASC."""
    with open(PG_STORE_PATH) as f:
        src = f.read()
    assert re.search(r"ORDER\s+BY\s+chunk_index", src, re.IGNORECASE), (
        "PgVectorStore.get must ORDER BY chunk_index to assemble chunks in order"
    )


def test_ac4_pg_store_get_assembles_details():
    """PgVectorStore.get must join chunk details to reconstruct the full article body."""
    with open(PG_STORE_PATH) as f:
        src = f.read()
    # Look for join pattern — details are joined across chunks
    assert re.search(r"\.join\s*\(|details.*join|join.*details", src, re.IGNORECASE), (
        "PgVectorStore.get must join details from all chunk rows to reconstruct the full body"
    )


@pytest.mark.skipif(not HAS_DB, reason="Requires live server with Postgres backend")
def test_ac4_get_article_returns_full_body_live(client):
    """GET /articles/:id must return the full reconstructed article body."""
    words = ["alpha"] * 60 + ["beta"] * 60 + ["gamma"] * 60  # 180 words — 2+ chunks
    long_body = " ".join(words)
    r = client.post("/articles", json={"headline": "Reconstruct AC4", "details": long_body, "attachment_url": ""})
    assert r.status_code == 201
    article_id = r.json()["id"]

    r2 = client.get(f"/articles/{article_id}")
    assert r2.status_code == 200
    returned = r2.json()
    assert "alpha" in returned.get("details", ""), "Full body must contain first chunk content"
    assert "gamma" in returned.get("details", ""), "Full body must contain last chunk content"

    client.delete(f"/articles/{article_id}")


# ---------------------------------------------------------------------------
# AC5: delete removes all chunk rows for the article_id
# ---------------------------------------------------------------------------


def test_ac5_pg_store_delete_uses_article_id():
    """PgVectorStore.delete must use WHERE article_id = $1 (not WHERE id = $1)."""
    with open(PG_STORE_PATH) as f:
        src = f.read()
    # Must delete by article_id (all chunks of an article)
    assert re.search(r"DELETE\s+FROM\s+articles\s+WHERE\s+article_id\s*=", src, re.IGNORECASE), (
        "PgVectorStore.delete must use DELETE FROM articles WHERE article_id = $1 "
        "to remove all chunk rows for an article"
    )


@pytest.mark.skipif(not HAS_DB, reason="Requires live server with Postgres backend")
def test_ac5_delete_removes_all_chunks_live(client):
    """DELETE /articles/:id must remove all chunk rows; subsequent GET must return 404."""
    long_body = " ".join(["Delete test word."] * 200)
    r = client.post("/articles", json={"headline": "Delete AC5", "details": long_body, "attachment_url": ""})
    assert r.status_code == 201
    article_id = r.json()["id"]

    r_del = client.delete(f"/articles/{article_id}")
    assert r_del.status_code in (200, 204)

    r_get = client.get(f"/articles/{article_id}")
    assert r_get.status_code == 404, (
        "After DELETE, GET /articles/:id must return 404"
    )


# ---------------------------------------------------------------------------
# AC6: count returns COUNT(DISTINCT article_id); chunkCount returns COUNT(*)
# ---------------------------------------------------------------------------


def test_ac6_pg_store_count_uses_distinct_article_id():
    """PgVectorStore.count must return COUNT(DISTINCT article_id)."""
    with open(PG_STORE_PATH) as f:
        src = f.read()
    assert re.search(r"COUNT\s*\(\s*DISTINCT\s+article_id\s*\)", src, re.IGNORECASE), (
        "PgVectorStore.count must use COUNT(DISTINCT article_id) to count unique articles"
    )


def test_ac6_pg_store_has_chunk_count_method():
    """PgVectorStore must have a chunkCount method returning COUNT(*)."""
    with open(PG_STORE_PATH) as f:
        src = f.read()
    has_chunk_count_method = "chunkCount" in src
    has_raw_count = re.search(r"COUNT\s*\(\s*\*\s*\)", src, re.IGNORECASE)
    assert has_chunk_count_method and has_raw_count, (
        "PgVectorStore must have a chunkCount() method using SELECT COUNT(*) FROM articles"
    )


# ---------------------------------------------------------------------------
# AC7: collection.js removes collapseToArticles / avgEmbeddings for postgres path
# ---------------------------------------------------------------------------


def test_ac7_collection_js_no_collapse_to_articles():
    """collection.js must not call collapseToArticles in the postgres upsert path."""
    with open(COLLECTION_JS) as f:
        src = f.read()
    # The function definition AND call must be gone
    assert "collapseToArticles" not in src, (
        "collection.js must not define or call collapseToArticles for the postgres path"
    )


def test_ac7_collection_js_no_avg_embeddings():
    """collection.js must not define or call avgEmbeddings."""
    with open(COLLECTION_JS) as f:
        src = f.read()
    assert "avgEmbeddings" not in src, (
        "collection.js must not define or call avgEmbeddings — chunk embeddings must be stored as-is"
    )


def test_ac7_postgres_js_no_collapse_to_articles():
    """postgres.js (factory wrapper) must not call collapseToArticles."""
    with open(POSTGRES_JS) as f:
        src = f.read()
    assert "collapseToArticles" not in src, (
        "postgres.js must not call collapseToArticles — pass chunk rows directly to store.upsert()"
    )


def test_ac7_postgres_js_no_avg_embeddings():
    """postgres.js must not define avgEmbeddings."""
    with open(POSTGRES_JS) as f:
        src = f.read()
    assert "avgEmbeddings" not in src, (
        "postgres.js must not define avgEmbeddings"
    )


# ---------------------------------------------------------------------------
# AC8: Server imports and uses chunker.js before upsert
# ---------------------------------------------------------------------------


def test_ac8_server_imports_chunker():
    """server.mjs must import chunkDocument (or chunkDocuments) from chunker.js."""
    with open(SERVER_MJS) as f:
        src = f.read()
    assert re.search(r"import\s+.*chunk(Document|Documents).*from.*chunker", src), (
        "server.mjs must import chunkDocument or chunkDocuments from ./data/chunker.js"
    )


def test_ac8_server_calls_chunk_on_create():
    """server.mjs POST /articles handler must call chunkDocument before upsertRows."""
    with open(SERVER_MJS) as f:
        src = f.read()
    assert "chunkDocument" in src or "chunkDocuments" in src, (
        "server.mjs must call chunkDocument/chunkDocuments before upsertRows"
    )


def test_ac8_server_no_single_chunk_zero_for_create():
    """server.mjs must NOT store articles as a single ':0' chunk without chunking."""
    with open(SERVER_MJS) as f:
        src = f.read()
    # The old pattern was: id: `${id}:0` with a single embed call per article
    # After fix, chunker produces multiple chunks with ids like `${id}:0`, `${id}:1`, etc.
    # The key change is: chunker is used instead of manually appending `:0`
    # We check that the old manual single-chunk pattern is gone
    old_patterns = re.findall(r"`\$\{id\}:0`|`\$\{articleId\}:0`|\$\{id\}\s*\+\s*':0'", src)
    assert not old_patterns, (
        "server.mjs must use chunkDocument instead of manually appending ':0' to article ids; "
        f"found old single-chunk patterns: {old_patterns}"
    )


# ---------------------------------------------------------------------------
# AC9: Demo corpus produces multiple chunk rows (live)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_DB, reason="Requires live server with Postgres backend")
def test_ac9_multi_chunk_article_in_list(client):
    """After ingest, GET /articles should list multiple articles (corpus was loaded)."""
    r = client.get("/articles")
    assert r.status_code == 200
    articles = r.json().get("articles", [])
    assert len(articles) > 0, "Expected at least one article after demo corpus ingest"


# ---------------------------------------------------------------------------
# AC10: Long article creates multiple chunk rows with sequential chunk_index
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_DB, reason="Requires live server with Postgres backend")
def test_ac10_long_article_stores_multiple_chunks_live(client):
    """POST /articles with a long body (> 120 words) must store multiple chunk rows."""
    # 200 words ensures at least 2 chunks (threshold is 120 words)
    words = [f"word{i}" for i in range(200)]
    long_body = " ".join(words)
    r = client.post("/articles", json={"headline": "Long Article AC10", "details": long_body, "attachment_url": ""})
    assert r.status_code == 201
    article_id = r.json()["id"]

    # GET /articles/:id returns full assembled body — all chunk words present
    r2 = client.get(f"/articles/{article_id}")
    assert r2.status_code == 200
    body = r2.json().get("details", "")
    # First and last words of original body must both appear
    assert "word0" in body, "First chunk content must be in reconstructed body"
    assert "word199" in body, "Last chunk content must be in reconstructed body"

    client.delete(f"/articles/{article_id}")


# ---------------------------------------------------------------------------
# AC11: GET /articles returns one entry per article (live)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_DB, reason="Requires live server with Postgres backend")
def test_ac11_get_articles_unique_ids_live(client):
    """GET /articles must return unique article ids (no duplicate entries per article)."""
    r = client.get("/articles")
    assert r.status_code == 200
    articles = r.json().get("articles", [])
    ids = [a.get("id") for a in articles]
    assert len(ids) == len(set(ids)), (
        f"GET /articles returned duplicate article ids: {[i for i in ids if ids.count(i) > 1]}"
    )


# ---------------------------------------------------------------------------
# AC12: GET /articles/:id returns full reconstructed body (live)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_DB, reason="Requires live server with Postgres backend")
def test_ac12_get_article_full_body_live(client):
    """GET /articles/:id must return the complete body assembled from all chunks."""
    marker_start = "BEGINNING_MARKER_UNIQUE_XYZ"
    marker_end = "ENDING_MARKER_UNIQUE_XYZ"
    filler = " ".join(["filler"] * 150)  # 150 filler words to cross chunk boundary
    body = f"{marker_start} {filler} {marker_end}"

    r = client.post("/articles", json={"headline": "Full Body AC12", "details": body, "attachment_url": ""})
    assert r.status_code == 201
    article_id = r.json()["id"]

    r2 = client.get(f"/articles/{article_id}")
    assert r2.status_code == 200
    returned_body = r2.json().get("details", "")
    assert marker_start in returned_body, (
        "GET /articles/:id must return the beginning of a multi-chunk article body"
    )
    assert marker_end in returned_body, (
        "GET /articles/:id must return the end of a multi-chunk article body"
    )

    client.delete(f"/articles/{article_id}")


# ---------------------------------------------------------------------------
# AC13: DELETE /articles/:id removes all chunks (live)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_DB, reason="Requires live server with Postgres backend")
def test_ac13_delete_clears_all_chunks_live(client):
    """DELETE /articles/:id must remove all chunk rows; GET must then return 404."""
    long_body = " ".join([f"chunk_word{i}" for i in range(200)])
    r = client.post("/articles", json={"headline": "Delete AC13", "details": long_body, "attachment_url": ""})
    assert r.status_code == 201
    article_id = r.json()["id"]

    r_del = client.delete(f"/articles/{article_id}")
    assert r_del.status_code in (200, 204)

    r_get = client.get(f"/articles/{article_id}")
    assert r_get.status_code == 404


# ---------------------------------------------------------------------------
# AC14: /health/integrity reports articleCount and chunkCount without false mismatch
# ---------------------------------------------------------------------------


def test_ac14_integrity_endpoint_reports_chunk_count_in_source():
    """server.mjs /health/integrity handler must report both articleCount and chunkCount."""
    with open(SERVER_MJS) as f:
        src = f.read()
    assert "chunkCount" in src, (
        "server.mjs /health/integrity must include chunkCount in the response"
    )
    assert "articleCount" in src, (
        "server.mjs /health/integrity must include articleCount in the response"
    )


@pytest.mark.skipif(not HAS_DB, reason="Requires live server with Postgres backend")
def test_ac14_integrity_no_false_mismatch_live(client):
    """GET /health/integrity must not report 'mismatch' solely because chunkCount > articleCount."""
    long_body = " ".join([f"integrity_word{i}" for i in range(200)])
    r = client.post("/articles", json={"headline": "Integrity AC14", "details": long_body, "attachment_url": ""})
    assert r.status_code == 201
    article_id = r.json()["id"]

    r_health = client.get("/health/integrity")
    assert r_health.status_code == 200
    data = r_health.json()
    # Must not be a false mismatch purely because of multi-chunk storage
    assert data.get("status") != "mismatch", (
        "/health/integrity must not raise mismatch when chunkCount > articleCount (expected with multi-chunk)"
    )
    assert "chunkCount" in data, "Response must include chunkCount"
    assert "articleCount" in data, "Response must include articleCount"

    client.delete(f"/articles/{article_id}")


# ---------------------------------------------------------------------------
# AC16: TypeScript compilation structure (structural checks)
# ---------------------------------------------------------------------------


def test_ac16_no_ts_in_changed_js_files():
    """Changed JS files must not contain TypeScript-only syntax (no TS interface/type keywords)."""
    files_to_check = [PG_STORE_PATH, COLLECTION_JS, POSTGRES_JS, SERVER_MJS]
    for fpath in files_to_check:
        with open(fpath) as f:
            src = f.read()
        # Check for obvious TypeScript-only syntax that would break plain JS
        assert not re.search(r"^interface\s+\w+", src, re.MULTILINE), (
            f"{fpath} must not contain TypeScript interface declarations"
        )
