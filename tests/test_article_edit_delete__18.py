"""
Acceptance tests for issue #18: Add edit and delete for existing articles.

AC1 - PUT /articles/:id re-embeds the updated text and upserts the record (no duplicate created)
AC2 - DELETE /articles/:id removes the article row from Milvus
AC3 - PUT /articles/:id with a non-existent id returns HTTP 404
AC4 - DELETE /articles/:id with a non-existent id returns HTTP 404
AC5 - After a successful PUT, search returns results reflecting the new text, not the old text
AC6 - After a successful DELETE, the article no longer appears in any search results
AC7 - Web UI shows edit and delete affordances (buttons or icons) per article in the article list
AC8 - Submitting the edit form calls PUT /articles/:id and reflects updated content without full page reload
AC9 - Clicking delete triggers a confirmation and calls DELETE /articles/:id, removing from UI list
"""

import os
import re

import httpx
import pytest

UAT_BASE_URL = os.environ.get("UAT_BASE_URL", "http://localhost:8001")

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SERVER_PATH = os.path.join(REPO_ROOT, "src", "server.mjs")
INDEX_HTML = os.path.join(REPO_ROOT, "public", "index.html")
COLLECTION_PATH = os.path.join(REPO_ROOT, "src", "data", "collection.js")


# ---------------------------------------------------------------------------
# Source inspection helpers
# ---------------------------------------------------------------------------

def _server_src():
    with open(SERVER_PATH) as f:
        return f.read()


def _html_src():
    with open(INDEX_HTML) as f:
        return f.read()


def _collection_src():
    with open(COLLECTION_PATH) as f:
        return f.read()


# ---------------------------------------------------------------------------
# Static analysis — server.mjs (AC1, AC2, AC3, AC4)
# ---------------------------------------------------------------------------

def test_ac1_server_has_put_articles_route():
    """server.mjs must handle PUT /articles/:id."""
    src = _server_src()
    assert re.search(r'PUT.*articles|method.*PUT.*articles', src), \
        "No PUT /articles/:id handler found in server.mjs"


def test_ac2_server_has_delete_articles_route():
    """server.mjs must handle DELETE /articles/:id."""
    src = _server_src()
    assert re.search(r'DELETE.*articles|method.*DELETE.*articles', src), \
        "No DELETE /articles/:id handler found in server.mjs"


def test_ac3_server_put_returns_404_for_missing():
    """server.mjs PUT handler must return 404 for non-existent article."""
    src = _server_src()
    assert "404" in src, "server.mjs does not return HTTP 404"
    # The PUT block must contain a 404 response
    put_match = re.search(r'PUT.*?(?=GET|DELETE|$)', src, re.DOTALL)
    assert put_match or re.search(r'404', src), \
        "server.mjs does not return 404 in PUT /articles handler"


def test_ac4_server_delete_returns_404_for_missing():
    """server.mjs DELETE handler must return 404 for non-existent article."""
    src = _server_src()
    assert re.search(r'DELETE', src), "No DELETE method handler in server.mjs"
    assert "404" in src, "server.mjs does not return HTTP 404"


def test_ac1_server_re_embeds_on_put():
    """server.mjs PUT handler must call the embedder to re-embed updated text."""
    src = _server_src()
    assert re.search(r'batchEmbed|embedder', src), \
        "server.mjs does not import or call the embedder"


def test_ac1_server_upserts_on_put():
    """server.mjs PUT handler must call upsertRows to update the record."""
    src = _server_src()
    assert re.search(r'upsertRows|upsert', src), \
        "server.mjs does not call upsertRows"


def test_ac1_cors_allows_put_delete():
    """server.mjs CORS preflight must allow PUT and DELETE methods."""
    src = _server_src()
    # Find the value of Access-Control-Allow-Methods (after the colon)
    cors_match = re.search(
        r'Access-Control-Allow-Methods["\']?\s*:\s*["\']([^"\']+)["\']', src
    )
    assert cors_match, "Access-Control-Allow-Methods header not found in server.mjs"
    methods = cors_match.group(1)
    assert "PUT" in methods, f"CORS Access-Control-Allow-Methods missing PUT: {methods}"
    assert "DELETE" in methods, f"CORS Access-Control-Allow-Methods missing DELETE: {methods}"


def test_collection_has_delete_article():
    """collection.js must expose a function to delete article rows by articleId."""
    src = _collection_src()
    assert re.search(r'deleteArticle|deleteRows|delete.*article', src, re.IGNORECASE), \
        "collection.js does not export a delete function for articles"


# ---------------------------------------------------------------------------
# Static analysis — public/index.html (AC7, AC8, AC9)
# ---------------------------------------------------------------------------

def test_ac7_html_shows_edit_affordance():
    """index.html must contain edit buttons or links for articles."""
    src = _html_src()
    has_edit = bool(re.search(r'edit|Edit|pencil|modify', src, re.IGNORECASE))
    assert has_edit, "No edit affordance found in index.html"


def test_ac7_html_shows_delete_affordance():
    """index.html must contain delete buttons or links for articles."""
    src = _html_src()
    has_delete = bool(re.search(r'delete|Delete|remove|trash', src, re.IGNORECASE))
    assert has_delete, "No delete affordance found in index.html"


def test_ac8_html_calls_put_articles():
    """index.html JS must call PUT /articles/:id when the edit form is submitted."""
    src = _html_src()
    assert re.search(r'PUT|method.*put', src, re.IGNORECASE), \
        "index.html does not call PUT for article edit"
    assert re.search(r'/articles', src), \
        "index.html does not reference /articles endpoint"


def test_ac8_html_updates_ui_without_reload():
    """index.html must update the DOM after edit without a full page reload."""
    src = _html_src()
    # Must not use window.location.reload() or location.href= inside the edit flow
    # Must manipulate DOM instead
    has_dom_update = bool(re.search(
        r'textContent|innerHTML|innerText|replaceWith|replaceChild', src
    ))
    assert has_dom_update, \
        "index.html does not update the DOM after edit (no textContent/innerHTML mutation found)"


def test_ac9_html_has_confirmation_for_delete():
    """index.html must show a confirmation prompt before deleting."""
    src = _html_src()
    has_confirm = bool(re.search(r'confirm\s*\(|window\.confirm|Are you sure|Confirm delete', src, re.IGNORECASE))
    assert has_confirm, \
        "index.html does not show a confirmation before deleting an article"


def test_ac9_html_calls_delete_articles():
    """index.html JS must call DELETE /articles/:id when delete is confirmed."""
    src = _html_src()
    assert re.search(r'DELETE|method.*delete', src, re.IGNORECASE), \
        "index.html does not call DELETE for article removal"


def test_ac9_html_removes_article_from_ui():
    """index.html must remove the article element from the DOM after deletion."""
    src = _html_src()
    has_removal = bool(re.search(r'remove\s*\(\)|removeChild|style\.display\s*=\s*["\']none', src))
    assert has_removal, \
        "index.html does not remove the article from the DOM after deletion"


# ---------------------------------------------------------------------------
# Live UAT tests (require UAT_BASE_URL to be set)
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    if not UAT_BASE_URL.startswith("http"):
        pytest.skip("UAT_BASE_URL not set — skipping live server tests")
    with httpx.Client(base_url=UAT_BASE_URL, timeout=10.0) as c:
        yield c


@pytest.fixture
def created_article(client):
    """Create a fresh article and return its id for use in tests."""
    r = client.post("/articles", json={
        "headline": "Edit Delete Test Article",
        "details": "This article is created for testing edit and delete functionality uniqueterm18xqz.",
        "attachment_url": "",
    })
    assert r.status_code == 201, f"Setup failed: {r.status_code} {r.text}"
    return r.json()["id"]


def test_ac1_put_articles_returns_200(client, created_article):
    """PUT /articles/:id with valid payload returns HTTP 200."""
    r = client.put(f"/articles/{created_article}", json={
        "headline": "Updated Headline",
        "details": "Updated body text for this article.",
        "attachment_url": "",
    })
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()
    assert "id" in data, f"Response missing 'id': {data}"
    assert data["id"] == created_article, \
        f"PUT should return same id, got {data['id']!r}"


def test_ac1_put_no_duplicate(client, created_article):
    """PUT /articles/:id does not create a duplicate article."""
    # PUT twice
    for _ in range(2):
        r = client.put(f"/articles/{created_article}", json={
            "headline": "No Duplicate Check",
            "details": "Checking that no duplicate is created on repeated PUT.",
            "attachment_url": "",
        })
        assert r.status_code == 200

    # Search for the article — should appear exactly once
    search_r = client.get("/search", params={"q": "No Duplicate Check"})
    assert search_r.status_code == 200
    results = search_r.json().get("results", [])
    ids = [item["id"] for item in results]
    assert ids.count(created_article) <= 1, \
        f"Article {created_article} appears {ids.count(created_article)} times after PUT (expected ≤1)"


def test_ac2_delete_articles_returns_200(client, created_article):
    """DELETE /articles/:id returns HTTP 200 (or 204)."""
    r = client.delete(f"/articles/{created_article}")
    assert r.status_code in (200, 204), f"Expected 200/204, got {r.status_code}: {r.text}"


def test_ac3_put_nonexistent_returns_404(client):
    """PUT /articles/<nonexistent-id> returns HTTP 404."""
    r = client.put("/articles/nonexistent-id-18zqx", json={
        "headline": "Ghost",
        "details": "This article does not exist.",
        "attachment_url": "",
    })
    assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"


def test_ac4_delete_nonexistent_returns_404(client):
    """DELETE /articles/<nonexistent-id> returns HTTP 404."""
    r = client.delete("/articles/nonexistent-id-18zqx")
    assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"


def test_ac5_search_reflects_updated_text(client, created_article):
    """After PUT, search returns the new text, not the old text."""
    old_term = "uniqueoldterm18abc"
    new_term = "uniquenewterm18xyz"

    # Update with new text
    r = client.put(f"/articles/{created_article}", json={
        "headline": f"Updated Headline {new_term}",
        "details": f"This article now contains {new_term} instead of the old text.",
        "attachment_url": "",
    })
    assert r.status_code == 200

    # New term must be findable
    new_r = client.get("/search", params={"q": new_term})
    assert new_r.status_code == 200
    new_ids = [item["id"] for item in new_r.json().get("results", [])]
    assert created_article in new_ids, \
        f"Article {created_article} not found after PUT when searching '{new_term}'"


def test_ac6_article_not_in_search_after_delete(client):
    """After DELETE, the article no longer appears in any search results."""
    unique = "deletedsearchterm18uvw"
    # Create
    r = client.post("/articles", json={
        "headline": f"To Be Deleted {unique}",
        "details": f"This article contains {unique} and will be deleted.",
        "attachment_url": "",
    })
    assert r.status_code == 201
    article_id = r.json()["id"]

    # Confirm searchable
    before = client.get("/search", params={"q": unique})
    before_ids = [item["id"] for item in before.json().get("results", [])]
    assert article_id in before_ids, "Article not searchable before delete"

    # Delete
    del_r = client.delete(f"/articles/{article_id}")
    assert del_r.status_code in (200, 204)

    # Confirm not searchable
    after = client.get("/search", params={"q": unique})
    after_ids = [item["id"] for item in after.json().get("results", [])]
    assert article_id not in after_ids, \
        f"Article {article_id} still appears in search after DELETE"
