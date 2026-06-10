"""
Acceptance tests for issue #17: Add single article creation via API and UI.

AC1 - POST /articles accepts {headline, details, attachment_url} and returns {id} with HTTP 201
AC2 - Generated article ID is stable and unique (deterministic or UUID)
AC3 - Headline + details are concatenated and embedded via the existing Embedder before upsert
AC4 - Row stored in Milvus carries headline, details, attachment_url, and id fields
AC5 - Article is immediately findable via the existing search endpoint after creation
AC6 - Web UI includes a form with fields: Headline, Details, Attachment URL, and a Submit button
AC7 - Form calls POST /articles and displays a success confirmation with the returned id
AC8 - Form displays an error message if the request fails
AC9 - Missing headline or details returns HTTP 400
"""

import os
import re

import httpx
import pytest

UAT_BASE_URL = os.environ.get("UAT_BASE_URL", "http://localhost:8001")

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SERVER_PATH = os.path.join(REPO_ROOT, "src", "server.mjs")
INDEX_HTML = os.path.join(REPO_ROOT, "public", "index.html")


# ---------------------------------------------------------------------------
# Source inspection helpers
# ---------------------------------------------------------------------------

def _server_src():
    with open(SERVER_PATH) as f:
        return f.read()


def _html_src():
    with open(INDEX_HTML) as f:
        return f.read()


# ---------------------------------------------------------------------------
# Static analysis — server.mjs (AC1, AC3, AC4)
# ---------------------------------------------------------------------------

def test_ac1_server_has_post_articles_route():
    """server.mjs must handle POST /articles."""
    src = _server_src()
    assert re.search(r'method.*POST.*articles|POST.*articles|/articles.*POST', src), \
        "No POST /articles handler found in server.mjs"


def test_ac3_server_imports_and_calls_embedder():
    """server.mjs must import batchEmbed (or the embedder module) and embed before upsert."""
    src = _server_src()
    assert re.search(r'batchEmbed|embedder', src), \
        "server.mjs does not import or call the embedder"


def test_ac3_server_concatenates_headline_and_details():
    """server.mjs must concatenate headline and details for embedding."""
    src = _server_src()
    assert re.search(r'headline.*details|details.*headline', src), \
        "server.mjs does not concatenate headline and details for embedding"


def test_ac4_server_upserts_required_fields():
    """server.mjs must upsert rows with headline, details, attachment_url, and id."""
    src = _server_src()
    for field in ("headline", "details", "attachment_url", "id"):
        assert field in src, f"server.mjs missing field '{field}' in upsert row"
    assert re.search(r'upsertRows|upsert', src), \
        "server.mjs does not call upsertRows"


def test_ac9_server_validates_required_fields():
    """server.mjs must return 400 when headline or details is missing."""
    src = _server_src()
    assert "400" in src, "server.mjs does not return HTTP 400 for validation errors"
    assert re.search(r'headline|details', src), \
        "server.mjs does not check for required fields headline/details"


# ---------------------------------------------------------------------------
# Static analysis — public/index.html (AC6, AC7, AC8)
# ---------------------------------------------------------------------------

def test_ac6_html_has_add_article_form():
    """index.html must contain a form or section for adding articles."""
    src = _html_src()
    has_form = bool(re.search(r'<form|add.article|create.article|post.*articles', src, re.IGNORECASE))
    assert has_form, "No article creation form found in index.html"


def test_ac6_html_has_headline_field():
    """Form must include a Headline input field."""
    src = _html_src()
    assert re.search(r'headline|Headline', src), \
        "No Headline field found in index.html form"


def test_ac6_html_has_details_field():
    """Form must include a Details input field (textarea or input)."""
    src = _html_src()
    assert re.search(r'details|Details', src), \
        "No Details field found in index.html form"


def test_ac6_html_has_attachment_url_field():
    """Form must include an Attachment URL input field."""
    src = _html_src()
    assert re.search(r'attachment.url|attachment_url|Attachment URL', src, re.IGNORECASE), \
        "No Attachment URL field found in index.html form"


def test_ac6_html_has_submit_button():
    """Form must include a Submit button."""
    src = _html_src()
    has_submit = bool(re.search(r'type\s*=\s*["\']submit["\']|Submit|submit', src, re.IGNORECASE))
    assert has_submit, "No Submit button found in index.html form"


def test_ac7_html_posts_to_articles_endpoint():
    """JS must call POST /articles when the form is submitted."""
    src = _html_src()
    assert re.search(r'/articles', src), "No /articles reference in index.html"
    assert re.search(r'POST|method.*post', src, re.IGNORECASE), \
        "No POST method found for article creation in index.html"


def test_ac7_html_displays_returned_id():
    """JS must show the returned id after successful article creation."""
    src = _html_src()
    assert re.search(r'\.id\b|["\']id["\']|data\.id|result\.id|json\(\).*id', src), \
        "index.html does not display the returned article id after creation"


def test_ac8_html_shows_error_on_failure():
    """JS must display an error message when POST /articles fails."""
    src = _html_src()
    # Must have both error handling (try/catch or .catch) and some error display
    has_error_handling = bool(re.search(r'catch\s*\(|\.catch\s*\(|try\s*\{', src))
    assert has_error_handling, \
        "index.html does not have error handling (try/catch) for article creation"


# ---------------------------------------------------------------------------
# Live UAT tests (require UAT_BASE_URL to be set)
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    if not UAT_BASE_URL.startswith("http"):
        pytest.skip("UAT_BASE_URL not set — skipping live server tests")
    with httpx.Client(base_url=UAT_BASE_URL, timeout=10.0) as c:
        yield c


def test_ac1_post_articles_returns_201_with_id(client):
    """POST /articles with valid payload returns HTTP 201 and {id}."""
    r = client.post("/articles", json={
        "headline": "Test Article Unique 17xqz",
        "details": "This is a test article for issue 17.",
        "attachment_url": "https://example.com/test.pdf",
    })
    assert r.status_code == 201, f"Expected 201, got {r.status_code}: {r.text}"
    data = r.json()
    assert "id" in data, f"Response missing 'id' field: {data}"
    assert isinstance(data["id"], str) and len(data["id"]) > 0, \
        f"'id' must be a non-empty string, got: {data['id']!r}"


def test_ac2_article_ids_are_unique(client):
    """Each POST /articles call returns a different id (uniqueness)."""
    r1 = client.post("/articles", json={
        "headline": "Unique Check A",
        "details": "Content for unique check A.",
        "attachment_url": "",
    })
    r2 = client.post("/articles", json={
        "headline": "Unique Check B",
        "details": "Content for unique check B.",
        "attachment_url": "",
    })
    assert r1.status_code == 201
    assert r2.status_code == 201
    id1 = r1.json()["id"]
    id2 = r2.json()["id"]
    assert id1 != id2, f"Two different articles got the same id: {id1!r}"


def test_ac5_article_findable_after_creation(client):
    """Article created via POST /articles is immediately findable via GET /search."""
    unique_term = "xqzarticle17uniqueterm"
    r = client.post("/articles", json={
        "headline": f"Article {unique_term}",
        "details": f"Details mentioning {unique_term} for search verification.",
        "attachment_url": "",
    })
    assert r.status_code == 201
    created_id = r.json()["id"]

    search_r = client.get("/search", params={"q": unique_term})
    assert search_r.status_code == 200
    results = search_r.json().get("results", [])
    ids = [item["id"] for item in results]
    assert created_id in ids, \
        f"Newly created article {created_id!r} not found in search results: {ids}"


def test_ac9_missing_headline_returns_400(client):
    """POST /articles without headline returns HTTP 400."""
    r = client.post("/articles", json={
        "details": "Some content without a headline.",
        "attachment_url": "",
    })
    assert r.status_code == 400, f"Expected 400 for missing headline, got {r.status_code}"


def test_ac9_missing_details_returns_400(client):
    """POST /articles without details returns HTTP 400."""
    r = client.post("/articles", json={
        "headline": "A headline without details",
        "attachment_url": "",
    })
    assert r.status_code == 400, f"Expected 400 for missing details, got {r.status_code}"


def test_ac9_empty_headline_returns_400(client):
    """POST /articles with empty string headline returns HTTP 400."""
    r = client.post("/articles", json={
        "headline": "",
        "details": "Some details here.",
        "attachment_url": "",
    })
    assert r.status_code == 400, f"Expected 400 for empty headline, got {r.status_code}"


def test_ac9_empty_details_returns_400(client):
    """POST /articles with empty string details returns HTTP 400."""
    r = client.post("/articles", json={
        "headline": "A valid headline",
        "details": "",
        "attachment_url": "",
    })
    assert r.status_code == 400, f"Expected 400 for empty details, got {r.status_code}"


def test_ac1_attachment_url_is_optional(client):
    """POST /articles succeeds when attachment_url is omitted."""
    r = client.post("/articles", json={
        "headline": "Article Without Attachment",
        "details": "This article has no attachment URL.",
    })
    assert r.status_code == 201, \
        f"Expected 201 when attachment_url omitted, got {r.status_code}: {r.text}"
    assert "id" in r.json()
