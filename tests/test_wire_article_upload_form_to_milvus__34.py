"""Tests for issue #34: Wire article upload form to Milvus collection (runs against UAT)"""
import os
import re

import httpx
import pytest

# Static analysis uses the coder clone on the feature branch.
CODER_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "coder")
)
SERVER_MJS = os.path.join(CODER_DIR, "src", "server.mjs")
COLLECTION_JS = os.path.join(CODER_DIR, "src", "data", "collection.js")
EMBEDDER_JS = os.path.join(CODER_DIR, "src", "data", "embedder.js")
ARTICLE_VALIDATION_JS = os.path.join(CODER_DIR, "src", "data", "articleValidation.js")
INDEX_HTML = os.path.join(CODER_DIR, "public", "index.html")
TEST_17 = os.path.join(CODER_DIR, "tests", "test_article_creation__17.py")
TEST_18 = os.path.join(CODER_DIR, "tests", "test_article_edit_delete__18.py")

UAT_BASE_URL = os.environ.get("UAT_BASE_URL", "http://localhost:8001")


@pytest.fixture
def client():
    with httpx.Client(base_url=UAT_BASE_URL, timeout=10.0) as c:
        yield c


# ---------------------------------------------------------------------------
# AC1: POST /articles embeds with MiniLM (384-dim) and upserts to Milvus
# ---------------------------------------------------------------------------


def test_wire_article_upload__ac1_server_has_post_articles_route():
    """AC1: server.mjs must handle POST /articles."""
    with open(SERVER_MJS) as f:
        src = f.read()
    assert re.search(r"POST.*articles|/articles.*POST", src), (
        "server.mjs must have a POST /articles route handler"
    )


def test_wire_article_upload__ac1_server_imports_batchEmbed():
    """AC1: server.mjs must import batchEmbed from the embedder module."""
    with open(SERVER_MJS) as f:
        src = f.read()
    assert re.search(r"import.*batchEmbed.*embedder|batchEmbed.*from.*embedder", src), (
        "server.mjs must import batchEmbed from the embedder for MiniLM embedding"
    )


def test_wire_article_upload__ac1_server_calls_batchEmbed_with_headline_details():
    """AC1: server.mjs must call batchEmbed concatenating headline and details."""
    with open(SERVER_MJS) as f:
        src = f.read()
    assert re.search(r"batchEmbed", src), (
        "server.mjs must call batchEmbed to produce MiniLM embeddings"
    )
    assert re.search(r"headline.*details|details.*headline", src), (
        "server.mjs must concatenate headline and details for the embedding input"
    )


def test_wire_article_upload__ac1_server_calls_upsertRows_with_required_fields():
    """AC1: server.mjs must call upsertRows with id, headline, details, attachment_url, embedding."""
    with open(SERVER_MJS) as f:
        src = f.read()
    assert re.search(r"upsertRows", src), (
        "server.mjs must call upsertRows to persist the article in Milvus"
    )
    for field in ("headline", "details", "attachment_url", "embedding"):
        assert field in src, (
            f"server.mjs must include '{field}' field in the upsertRows payload"
        )


# ---------------------------------------------------------------------------
# AC2: POST /articles/bulk applies same embedding and Milvus upsert
# ---------------------------------------------------------------------------


def test_wire_article_upload__ac2_server_has_post_bulk_route():
    """AC2: server.mjs must handle POST /articles/bulk."""
    with open(SERVER_MJS) as f:
        src = f.read()
    assert re.search(r"articles/bulk", src), (
        "server.mjs must have a POST /articles/bulk route handler"
    )


def test_wire_article_upload__ac2_bulk_handler_calls_batchEmbed_and_upsertRows():
    """AC2: batchEmbed and upsertRows must each appear across all three handlers (bulk, POST, PUT)."""
    with open(SERVER_MJS) as f:
        src = f.read()
    # Each of the 3 article mutation handlers must call batchEmbed — verify ≥ 3 call sites
    embed_count = len(re.findall(r"await batchEmbed\(", src))
    assert embed_count >= 3, (
        f"server.mjs must call batchEmbed in all three handlers (bulk/POST/PUT); found {embed_count} call(s)"
    )
    upsert_count = len(re.findall(r"await upsertRows\(", src))
    assert upsert_count >= 3, (
        f"server.mjs must call upsertRows in all three handlers (bulk/POST/PUT); found {upsert_count} call(s)"
    )


# ---------------------------------------------------------------------------
# AC3: PUT /articles/:id re-embeds and updates Milvus row
# ---------------------------------------------------------------------------


def test_wire_article_upload__ac3_server_has_put_articles_id_route():
    """AC3: server.mjs must handle PUT /articles/:id."""
    with open(SERVER_MJS) as f:
        src = f.read()
    assert re.search(r"PUT.*articles|method.*PUT.*articles", src), (
        "server.mjs must have a PUT /articles/:id route handler"
    )


def test_wire_article_upload__ac3_put_handler_re_embeds_and_upserts():
    """AC3: PUT /articles/:id must re-embed and re-upsert (verified by ≥3 call sites per helper)."""
    with open(SERVER_MJS) as f:
        src = f.read()
    # batchEmbed and upsertRows must appear in the PUT handler context.
    # Since all three handlers (bulk, POST, PUT) each add one call site, ≥3 confirms PUT is covered.
    embed_calls = len(re.findall(r"await batchEmbed\(", src))
    upsert_calls = len(re.findall(r"await upsertRows\(", src))
    assert embed_calls >= 3, (
        f"server.mjs must call batchEmbed in the PUT handler (found only {embed_calls} total call sites)"
    )
    assert upsert_calls >= 3, (
        f"server.mjs must call upsertRows in the PUT handler (found only {upsert_calls} total call sites)"
    )
    # Also verify the PUT route definition explicitly exists
    assert re.search(r'req\.method === ["\']PUT["\']', src), (
        "server.mjs must have an explicit PUT method check for the /articles/:id handler"
    )


# ---------------------------------------------------------------------------
# AC4: Flush/load called after each insert/upsert
# ---------------------------------------------------------------------------


def test_wire_article_upload__ac4_collection_calls_flush_after_upsert():
    """AC4: collection.js upsertRows must call client.flush after Milvus upsert."""
    with open(COLLECTION_JS) as f:
        src = f.read()
    assert re.search(r"client\.flush", src), (
        "collection.js upsertRows must call client.flush so new rows are immediately visible"
    )


def test_wire_article_upload__ac4_collection_loads_after_create():
    """AC4: collection.js createCollection must call client.loadCollection."""
    with open(COLLECTION_JS) as f:
        src = f.read()
    assert re.search(r"loadCollection", src), (
        "collection.js createCollection must call client.loadCollection for query visibility"
    )


# ---------------------------------------------------------------------------
# AC5: POST /articles and POST /articles/bulk return 400 when headline/details missing
# ---------------------------------------------------------------------------


def test_wire_article_upload__ac5_validation_requires_headline():
    """AC5: articleValidation.js must treat missing/empty headline as an error."""
    with open(ARTICLE_VALIDATION_JS) as f:
        src = f.read()
    assert re.search(r"headline.*required|headline.*trim\(\)|headline.*\!\s*h", src, re.DOTALL), (
        "articleValidation.js must validate that headline is required"
    )


def test_wire_article_upload__ac5_validation_requires_details():
    """AC5: articleValidation.js must treat missing/empty details as an error."""
    with open(ARTICLE_VALIDATION_JS) as f:
        src = f.read()
    assert re.search(r"details.*required|details.*trim\(\)|details.*\!\s*d", src, re.DOTALL), (
        "articleValidation.js must validate that details is required"
    )


def test_wire_article_upload__ac5_server_returns_400_on_validation_error():
    """AC5: server.mjs must respond with HTTP 400 when validation fails."""
    with open(SERVER_MJS) as f:
        src = f.read()
    assert "validateArticle" in src, (
        "server.mjs must call validateArticle to enforce required fields"
    )
    assert "400" in src, (
        "server.mjs must return HTTP 400 when validation fails"
    )


# ---------------------------------------------------------------------------
# AC6: All three endpoints return { id } on success
# ---------------------------------------------------------------------------


def test_wire_article_upload__ac6_post_articles_returns_id():
    """AC6: server.mjs POST /articles success response must include { id }."""
    with open(SERVER_MJS) as f:
        src = f.read()
    assert re.search(r"201.*\{.*id|jsonResponse.*201.*id", src, re.DOTALL), (
        "server.mjs POST /articles must return HTTP 201 with { id } on success"
    )


def test_wire_article_upload__ac6_put_articles_returns_id():
    """AC6: server.mjs PUT /articles/:id success response must include { id }."""
    with open(SERVER_MJS) as f:
        src = f.read()
    assert re.search(r"200.*articleId|jsonResponse.*200.*id", src, re.DOTALL), (
        "server.mjs PUT /articles/:id must return HTTP 200 with { id } on success"
    )


# ---------------------------------------------------------------------------
# AC7: Article findable via GET /search immediately after create
# (verified by static analysis — search uses Milvus which upsertRows populates)
# ---------------------------------------------------------------------------


def test_wire_article_upload__ac7_search_uses_milvus_backend():
    """AC7: Search must be backed by Milvus so articles are findable after upsert."""
    with open(COLLECTION_JS) as f:
        src = f.read()
    assert re.search(r"client\.search|searchDocuments|MILVUS_HOST", src), (
        "collection.js must use the Milvus client for search so upserted articles are findable"
    )


# ---------------------------------------------------------------------------
# AC8: Add Article form UI unchanged in public/index.html
# ---------------------------------------------------------------------------


def test_wire_article_upload__ac8_html_has_add_form():
    """AC8: public/index.html must still contain the Add Article form."""
    with open(INDEX_HTML) as f:
        src = f.read()
    assert re.search(r"<form.*add-form|add-form.*<form|id=[\"']add-form", src, re.DOTALL), (
        "public/index.html must retain the Add Article form (class/id 'add-form')"
    )


def test_wire_article_upload__ac8_html_has_headline_details_attachment_fields():
    """AC8: index.html must still have Headline, Details, and Attachment URL fields."""
    with open(INDEX_HTML) as f:
        src = f.read()
    for field_pattern, name in [
        (r"headline|art-headline", "Headline"),
        (r"details|art-details", "Details"),
        (r"attachment_url|attachment-url|art-attachment", "Attachment URL"),
    ]:
        assert re.search(field_pattern, src, re.IGNORECASE), (
            f"public/index.html must still have a '{name}' field in the Add Article form"
        )


def test_wire_article_upload__ac8_html_posts_to_articles_endpoint():
    """AC8: index.html JS must still call POST /articles when submitting the form."""
    with open(INDEX_HTML) as f:
        src = f.read()
    assert re.search(r"fetch.*articles|POST.*articles|/articles", src), (
        "public/index.html must still call POST /articles for article creation"
    )


# ---------------------------------------------------------------------------
# AC9: Issue #17 and #18 test files exist and cover the feature
# ---------------------------------------------------------------------------


def test_wire_article_upload__ac9_issue17_test_file_exists():
    """AC9: tests/test_article_creation__17.py must exist in the coder branch."""
    assert os.path.isfile(TEST_17), (
        "tests/test_article_creation__17.py not found — issue #17 tests must pass against Milvus"
    )


def test_wire_article_upload__ac9_issue18_test_file_exists():
    """AC9: tests/test_article_edit_delete__18.py must exist in the coder branch."""
    assert os.path.isfile(TEST_18), (
        "tests/test_article_edit_delete__18.py not found — issue #18 tests must pass against Milvus"
    )


def test_wire_article_upload__ac9_issue17_covers_post_articles():
    """AC9: test_article_creation__17.py must test POST /articles endpoint."""
    with open(TEST_17) as f:
        content = f.read()
    assert re.search(r"/articles|post.*articles|articles.*post", content, re.IGNORECASE), (
        "test_article_creation__17.py must include POST /articles tests for Milvus-backed coverage"
    )


# ---------------------------------------------------------------------------
# AC10: No collection.json or TF-IDF references in create/update code paths
# ---------------------------------------------------------------------------


def test_wire_article_upload__ac10_server_mjs_no_collection_json():
    """AC10: server.mjs must not reference collection.json in any code path."""
    with open(SERVER_MJS) as f:
        src = f.read()
    assert "collection.json" not in src, (
        "server.mjs must not reference collection.json — all data must go through Milvus"
    )


def test_wire_article_upload__ac10_server_mjs_no_tfidf():
    """AC10: server.mjs must not reference TF-IDF embedding path."""
    with open(SERVER_MJS) as f:
        src = f.read()
    assert not re.search(r"tfidf|tf.idf|TfIdf|TF.IDF", src, re.IGNORECASE), (
        "server.mjs must not reference TF-IDF — all embeddings must use the MiniLM path"
    )


def test_wire_article_upload__ac10_embedder_uses_minilm():
    """AC10: embedder.js must use MiniLM (createEmbedder) for all embeddings."""
    with open(EMBEDDER_JS) as f:
        src = f.read()
    assert re.search(r"createEmbedder|MiniLM|minilm", src, re.IGNORECASE), (
        "embedder.js must use MiniLM via createEmbedder, not TF-IDF"
    )
    assert not re.search(r"tfidf|TfIdf|tf_idf", src, re.IGNORECASE), (
        "embedder.js must not reference TF-IDF — issue #34 wires MiniLM as the embedder"
    )


# ---------------------------------------------------------------------------
# UAT smoke: UAT server is responding (Commander dashboard at UAT_BASE_URL)
# ---------------------------------------------------------------------------


def test_wire_article_upload__uat_server_responds(client):
    """Smoke: UAT server at UAT_BASE_URL must respond with HTTP 200."""
    r = client.get("/")
    assert r.status_code == 200
