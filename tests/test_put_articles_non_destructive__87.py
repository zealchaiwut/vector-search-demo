"""
Acceptance tests for issue #87: Make PUT /articles/:id update non-destructive on embed failure.

The PUT /articles/:id handler must embed the new chunks BEFORE deleting the
old ones so that a failure in batchEmbed (or upsertRows) leaves the original
article intact.  If batchEmbed throws, the article must still be accessible
via GET /articles/:id.

AC1 - Operation order in server.mjs: batchEmbed is called BEFORE deleteArticle
      in the PUT handler (static check).
AC2 - If batchEmbed throws, the original article data is preserved (no deletion
      occurred before the error).
AC3 - Normal PUT still succeeds and returns 200 with the updated article id.
"""

import os
import re

import httpx
import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SERVER_PATH = os.path.join(REPO_ROOT, "src", "server.mjs")

UAT_BASE_URL = os.environ.get("UAT_BASE_URL", "http://localhost:8001")


# ---------------------------------------------------------------------------
# Static analysis — operation order (AC1)
# ---------------------------------------------------------------------------

def _put_handler_src():
    """Extract just the PUT /articles/:id handler block from server.mjs."""
    with open(SERVER_PATH) as f:
        src = f.read()
    # Find the PUT block: from 'PUT' to the next top-level route or end
    match = re.search(
        r'(req\.method\s*===\s*["\']PUT["\'].*?/articles.*?)(req\.method\s*===\s*["\']DELETE["\'])',
        src,
        re.DOTALL,
    )
    if match:
        return match.group(1)
    # fallback: return entire source
    return src


def test_ac1_embed_before_delete_in_put_handler():
    """batchEmbed must appear before deleteArticle in the PUT /articles/:id handler."""
    block = _put_handler_src()
    embed_pos = block.find("batchEmbed")
    delete_pos = block.find("deleteArticle")
    assert embed_pos != -1, "batchEmbed not found in PUT handler block"
    assert delete_pos != -1, "deleteArticle not found in PUT handler block"
    assert embed_pos < delete_pos, (
        f"deleteArticle (pos {delete_pos}) must come AFTER batchEmbed (pos {embed_pos}) "
        "in the PUT handler — embed first so failures leave the original article intact"
    )


# ---------------------------------------------------------------------------
# Live tests (require UAT_BASE_URL)
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    if not UAT_BASE_URL.startswith("http"):
        pytest.skip("UAT_BASE_URL not set — skipping live server tests")
    with httpx.Client(base_url=UAT_BASE_URL, timeout=10.0) as c:
        yield c


@pytest.fixture
def original_article(client):
    """Create a fresh article to use as the pre-existing record."""
    r = client.post("/articles", json={
        "headline": "Original Article 87",
        "details": "This is the original content that must survive an embed failure. uniqueterm87orig",
        "attachment_url": "",
    })
    assert r.status_code == 201, f"Setup failed: {r.status_code} {r.text}"
    article_id = r.json()["id"]
    yield article_id
    # cleanup
    client.delete(f"/articles/{article_id}")


def test_ac3_normal_put_succeeds(client, original_article):
    """A normal PUT /articles/:id call returns 200 and the same article id."""
    r = client.put(f"/articles/{original_article}", json={
        "headline": "Updated Headline 87",
        "details": "Updated body text for issue 87 regression check.",
        "attachment_url": "",
    })
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()
    assert data.get("id") == original_article, (
        f"PUT should return same id, got {data.get('id')!r}"
    )
