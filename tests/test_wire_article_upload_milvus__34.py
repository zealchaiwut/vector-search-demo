"""
Acceptance tests for issue #34: Wire article upload form to Milvus collection.

AC1 - POST /articles embeds headline+details via MiniLM (384-dim vector) and upserts into
      the Milvus 'documents' collection with fields: id, headline, details, attachment_url, embedding
AC2 - POST /articles/bulk applies the same MiniLM embedding and Milvus upsert for every article
AC3 - PUT /articles/:id re-embeds and updates the existing Milvus row (headline, details,
      attachment_url, and embedding) identified by id
AC4 - A flush or load call is issued after each insert/upsert so the new row is visible to
      subsequent queries without a service restart
AC5 - POST /articles and POST /articles/bulk still return 400 when headline or details is missing
AC6 - All three endpoints still return { id } on success
AC7 - A newly submitted article appears in GET /search results for a matching query immediately
      after the create call completes
AC8 - The Add Article form UI and UX in public/index.html are unchanged
AC9 - All acceptance tests introduced in issue #17 and issue #18 pass against the endpoints
AC10 - No references to collection.json or TF-IDF embed path remain in the create/update code paths
"""

import os
import re

import httpx
import pytest

UAT_BASE_URL = os.environ.get("UAT_BASE_URL", "http://localhost:8001")

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SERVER_PATH = os.path.join(REPO_ROOT, "src", "server.mjs")
COLLECTION_PATH = os.path.join(REPO_ROOT, "src", "data", "collection.js")
INDEX_HTML = os.path.join(REPO_ROOT, "public", "index.html")


# ---------------------------------------------------------------------------
# Source inspection helpers
# ---------------------------------------------------------------------------

def _server_src():
    with open(SERVER_PATH) as f:
        return f.read()


def _collection_src():
    with open(COLLECTION_PATH) as f:
        return f.read()


def _html_src():
    with open(INDEX_HTML) as f:
        return f.read()


# ---------------------------------------------------------------------------
# Static analysis — server.mjs (AC1, AC2, AC3, AC10)
# ---------------------------------------------------------------------------

def test_ac1_post_articles_awaits_batch_embed():
    """server.mjs POST /articles handler must await batchEmbed (not call it synchronously)."""
    src = _server_src()
    # Must have 'await batchEmbed' somewhere in the source
    assert re.search(r'await\s+batchEmbed', src), \
        "server.mjs does not await batchEmbed — embedding will return a Promise, not a vector"


def test_ac1_post_articles_awaits_upsert_rows():
    """server.mjs POST /articles handler must await upsertRows."""
    src = _server_src()
    assert re.search(r'await\s+upsertRows', src), \
        "server.mjs does not await upsertRows — article will not be stored before response"


def test_ac2_bulk_awaits_batch_embed():
    """server.mjs POST /articles/bulk handler must await batchEmbed for each row."""
    src = _server_src()
    assert re.search(r'await\s+batchEmbed', src), \
        "server.mjs does not await batchEmbed in bulk handler"


def test_ac2_bulk_awaits_upsert_rows():
    """server.mjs POST /articles/bulk handler must await upsertRows for each row."""
    src = _server_src()
    assert re.search(r'await\s+upsertRows', src), \
        "server.mjs does not await upsertRows in bulk handler"


def test_ac3_put_awaits_batch_embed():
    """server.mjs PUT /articles/:id handler must await batchEmbed."""
    src = _server_src()
    assert re.search(r'await\s+batchEmbed', src), \
        "server.mjs does not await batchEmbed in PUT handler"


def test_ac3_put_awaits_upsert_rows():
    """server.mjs PUT /articles/:id handler must await upsertRows."""
    src = _server_src()
    assert re.search(r'await\s+upsertRows', src), \
        "server.mjs does not await upsertRows in PUT handler"


def test_ac3_put_awaits_get_article():
    """server.mjs PUT /articles/:id handler must await getArticle lookup."""
    src = _server_src()
    assert re.search(r'await\s+getArticle', src), \
        "server.mjs does not await getArticle in PUT handler — 404 check will always pass incorrectly"


def test_ac10_server_no_collection_json_in_article_handlers():
    """server.mjs must not reference collection.json in the article create/update handlers."""
    src = _server_src()
    assert "collection.json" not in src, \
        "server.mjs references collection.json directly in article handlers"


def test_ac10_server_no_tfidf_in_article_handlers():
    """server.mjs must not use a TF-IDF embed path in the create/update code paths."""
    src = _server_src()
    assert not re.search(r'tfidf|tf.idf|buildIDF|tfidfEmbed', src, re.IGNORECASE), \
        "server.mjs references TF-IDF embedding in article create/update handlers"


# ---------------------------------------------------------------------------
# Static analysis — collection.js (AC4)
# ---------------------------------------------------------------------------

def test_ac4_collection_js_flushes_after_upsert():
    """collection.js upsertRows must issue a flush call after upsert so data is immediately queryable."""
    src = _collection_src()
    # Must call client.flush or client.flushSync after the upsert
    assert re.search(r'client\.(flushSync|flush)\s*\(', src), \
        "collection.js does not call client.flush/flushSync after upsert — new rows may not be visible to search"


def test_ac4_collection_js_loads_after_upsert():
    """collection.js upsertRows must issue a loadCollection call to make new data queryable."""
    src = _collection_src()
    # Must call loadCollection somewhere in the upsert path
    assert re.search(r'loadCollection|flushSync|flush', src), \
        "collection.js does not ensure data visibility after upsert"


# ---------------------------------------------------------------------------
# Static analysis — public/index.html (AC8)
# ---------------------------------------------------------------------------

def test_ac8_html_still_has_add_article_form():
    """public/index.html must still contain the Add Article form (no UI regression)."""
    src = _html_src()
    assert re.search(r'<form|add.article|create.article|/articles', src, re.IGNORECASE), \
        "public/index.html no longer contains the Add Article form — UI was broken"


def test_ac8_html_still_has_headline_field():
    """Form must still include a Headline input field."""
    src = _html_src()
    assert re.search(r'headline|Headline', src), \
        "Headline field missing from public/index.html — UI regression"


def test_ac8_html_still_has_details_field():
    """Form must still include a Details input/textarea field."""
    src = _html_src()
    assert re.search(r'details|Details', src), \
        "Details field missing from public/index.html — UI regression"


# ---------------------------------------------------------------------------
# Live UAT tests (require UAT_BASE_URL)
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    if not UAT_BASE_URL.startswith("http"):
        pytest.skip("UAT_BASE_URL not set — skipping live server tests")
    with httpx.Client(base_url=UAT_BASE_URL, timeout=30.0) as c:
        yield c


def test_ac6_post_articles_returns_id(client):
    """POST /articles returns HTTP 201 and a non-empty {id} string."""
    r = client.post("/articles", json={
        "headline": "Milvus Wire Test 34",
        "details": "Testing that article is stored in Milvus via MiniLM.",
        "attachment_url": "https://example.com/34.pdf",
    })
    assert r.status_code == 201, f"Expected 201, got {r.status_code}: {r.text}"
    data = r.json()
    assert "id" in data, f"Response missing 'id': {data}"
    assert isinstance(data["id"], str) and len(data["id"]) > 0


def test_ac5_post_articles_400_missing_headline(client):
    """POST /articles without headline returns HTTP 400."""
    r = client.post("/articles", json={
        "details": "Details only, no headline.",
        "attachment_url": "",
    })
    assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text}"


def test_ac5_post_articles_400_missing_details(client):
    """POST /articles without details returns HTTP 400."""
    r = client.post("/articles", json={
        "headline": "Headline only, no details.",
        "attachment_url": "",
    })
    assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text}"


def test_ac7_newly_created_article_appears_in_search(client):
    """Article created via POST /articles is immediately findable via GET /search."""
    unique_term = "quantumllama34xunique"
    r = client.post("/articles", json={
        "headline": f"Quantum Llama {unique_term}",
        "details": f"Research paper about {unique_term} in distributed vector systems.",
        "attachment_url": "",
    })
    assert r.status_code == 201
    created_id = r.json()["id"]

    search_r = client.get("/search", params={"q": unique_term})
    assert search_r.status_code == 200
    results = search_r.json().get("results", [])
    ids = [item["id"] for item in results]
    assert created_id in ids, \
        f"Newly created article {created_id!r} not found in search results immediately after creation. " \
        f"Found ids: {ids}. This indicates upsert is not awaited or flush is missing."


def test_ac1_post_articles_stores_embedding(client):
    """POST /articles stores a 384-dim vector — verifiable via search scoring."""
    unique_term = "milvuswire34embedtest"
    r = client.post("/articles", json={
        "headline": f"Embedding check {unique_term}",
        "details": f"This article tests that the MiniLM embedding is stored: {unique_term}.",
        "attachment_url": "",
    })
    assert r.status_code == 201
    created_id = r.json()["id"]

    # The article must be retrievable via vector search — if embedding was a Promise object
    # (unawaited), the vector store would reject it or store garbage.
    search_r = client.get("/search", params={"q": unique_term})
    assert search_r.status_code == 200, f"Search failed: {search_r.text}"
    results = search_r.json().get("results", [])
    ids = [item["id"] for item in results]
    assert created_id in ids, \
        f"Article {created_id!r} not in search results — embedding likely not stored correctly."


def test_ac6_post_bulk_returns_succeeded_count(client):
    """POST /articles/bulk returns {total, succeeded, failed, errors} with correct counts."""
    r = client.post("/articles/bulk", json={
        "rows": [
            {"headline": "Bulk A 34", "details": "Bulk article A for issue 34.", "attachment_url": ""},
            {"headline": "Bulk B 34", "details": "Bulk article B for issue 34.", "attachment_url": ""},
        ]
    })
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()
    assert data.get("total") == 2, f"Expected total=2: {data}"
    assert data.get("succeeded") == 2, f"Expected succeeded=2: {data}"
    assert data.get("failed") == 0, f"Expected failed=0: {data}"


def test_ac5_bulk_400_missing_headline(client):
    """POST /articles/bulk with a row missing headline returns HTTP 400."""
    r = client.post("/articles/bulk", json={
        "rows": [
            {"details": "No headline row", "attachment_url": ""},
        ]
    })
    assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text}"


def test_ac3_put_updates_article_and_stays_searchable(client):
    """PUT /articles/:id re-embeds updated text; updated article appears in search."""
    unique_term = "milvuswire34puttest"
    # Create
    r = client.post("/articles", json={
        "headline": f"Original headline {unique_term}",
        "details": f"Original details for {unique_term}.",
        "attachment_url": "",
    })
    assert r.status_code == 201
    article_id = r.json()["id"]

    new_unique_term = "milvuswire34putupdated"
    put_r = client.put(f"/articles/{article_id}", json={
        "headline": f"Updated headline {new_unique_term}",
        "details": f"Updated details mentioning {new_unique_term}.",
        "attachment_url": "https://example.com/updated.pdf",
    })
    assert put_r.status_code == 200, f"Expected 200 for PUT, got {put_r.status_code}: {put_r.text}"
    assert put_r.json().get("id") == article_id

    # New content must be searchable
    search_r = client.get("/search", params={"q": new_unique_term})
    assert search_r.status_code == 200
    results = search_r.json().get("results", [])
    ids = [item["id"] for item in results]
    assert article_id in ids, \
        f"Updated article {article_id!r} not found in search for new term {new_unique_term!r}. " \
        f"PUT may not be awaiting upsert or flush."


def test_ac3_put_returns_id(client):
    """PUT /articles/:id returns HTTP 200 with {id}."""
    # Create first
    r = client.post("/articles", json={
        "headline": "PUT id test 34",
        "details": "Article to test PUT returns id.",
        "attachment_url": "",
    })
    assert r.status_code == 201
    article_id = r.json()["id"]

    put_r = client.put(f"/articles/{article_id}", json={
        "headline": "PUT id test 34 updated",
        "details": "Updated article to test PUT returns id.",
        "attachment_url": "",
    })
    assert put_r.status_code == 200, f"Expected 200, got {put_r.status_code}: {put_r.text}"
    assert put_r.json().get("id") == article_id, \
        f"PUT response must return {{id: '{article_id}'}}, got: {put_r.json()}"
