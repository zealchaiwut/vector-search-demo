"""Tests for issue #33: Port article CRUD operations from file to Milvus (runs against UAT)"""
import os
import re

import httpx
import pytest

# Static analysis uses the coder clone on the feature branch.
CODER_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "coder")
)
COLLECTION_JS = os.path.join(CODER_DIR, "src", "data", "collection.js")
README_PATH = os.path.join(CODER_DIR, "README.md")
TEST_MILVUS_CLIENT = os.path.join(CODER_DIR, "tests", "test_milvus_client__2.py")
TEST_MILVUS_SCHEMA = os.path.join(CODER_DIR, "tests", "test_milvus_schema__3.py")
E2E_TEST_PATH = os.path.join(CODER_DIR, "tests", "test_article_crud_milvus__33.py")

UAT_BASE_URL = os.environ.get("UAT_BASE_URL", "http://localhost:8001")


@pytest.fixture
def client():
    with httpx.Client(base_url=UAT_BASE_URL, timeout=10.0) as c:
        yield c


# ---------------------------------------------------------------------------
# AC1: listArticles queries Milvus using an id-prefix expression
# ---------------------------------------------------------------------------


def test_port_article_crud_from_file_to_milvus__ac1_listArticles_uses_id_like():
    """AC1: listArticles must use 'id like \"%\"' Milvus filter expression."""
    with open(COLLECTION_JS) as f:
        src = f.read()
    assert re.search(r'id\s+like\s+["\']%["\']', src), (
        "collection.js listArticles must use Milvus filter 'id like \"%\"'"
    )


def test_port_article_crud_from_file_to_milvus__ac1_listArticles_uses_client_query():
    """AC1: listArticles must call client.query in the Milvus path."""
    with open(COLLECTION_JS) as f:
        src = f.read()
    assert re.search(r"client\.query", src), (
        "collection.js must call client.query for Milvus-backed listArticles"
    )


# ---------------------------------------------------------------------------
# AC2: getArticle retrieves from Milvus by id-prefix expression
# ---------------------------------------------------------------------------


def test_port_article_crud_from_file_to_milvus__ac2_getArticle_uses_id_prefix():
    """AC2: getArticle must filter by id-prefix expression (articleId:%)."""
    with open(COLLECTION_JS) as f:
        src = f.read()
    has_prefix_expr = bool(
        re.search(r'id\s+like\s+[`"\'].*:%', src)
    )
    assert has_prefix_expr, (
        "collection.js getArticle must use 'id like \"<articleId>:%\"' prefix expression"
    )


# ---------------------------------------------------------------------------
# AC3: deleteArticle removes from Milvus by id-prefix expression
# ---------------------------------------------------------------------------


def test_port_article_crud_from_file_to_milvus__ac3_deleteArticle_uses_client_delete():
    """AC3: deleteArticle must call client.delete for Milvus removal."""
    with open(COLLECTION_JS) as f:
        src = f.read()
    assert re.search(r"client\.delete", src), (
        "collection.js must call client.delete in the deleteArticle Milvus path"
    )


# ---------------------------------------------------------------------------
# AC4: collection.json not read by the three functions at runtime (Milvus path)
# ---------------------------------------------------------------------------


def test_port_article_crud_from_file_to_milvus__ac4_milvus_path_gated_on_env():
    """AC4: Milvus-backed paths must be gated on MILVUS_HOST to avoid file reads at runtime."""
    with open(COLLECTION_JS) as f:
        src = f.read()
    assert "MILVUS_HOST" in src, (
        "collection.js must gate Milvus vs file-backed paths on process.env.MILVUS_HOST"
    )


# ---------------------------------------------------------------------------
# AC5: README Architecture section describes Milvus-backed path, removes "unused" labels
# ---------------------------------------------------------------------------


def test_port_article_crud_from_file_to_milvus__ac5_readme_no_milvus_not_used_label():
    """AC5: README must not say 'Milvus is NOT used' or label it as otherwise unused."""
    with open(README_PATH) as f:
        content = f.read()
    assert "Milvus is NOT used" not in content, (
        "README still says 'Milvus is NOT used' — must be updated to reflect Milvus-backed storage"
    )
    assert "otherwise unused" not in content, (
        "README still labels Milvus components as 'otherwise unused'"
    )


def test_port_article_crud_from_file_to_milvus__ac5_readme_architecture_shows_milvus_primary():
    """AC5: README Architecture section must describe Milvus as the storage/search path."""
    with open(README_PATH) as f:
        content = f.read()
    arch_match = re.search(r"## Architecture.*?(?=\n## |\Z)", content, re.DOTALL)
    assert arch_match, "README.md has no '## Architecture' section"
    arch_section = arch_match.group()
    assert "Milvus" in arch_section, (
        "Architecture section does not mention Milvus as the storage path"
    )
    assert "Unwired (real backend)" not in arch_section, (
        "Architecture section still marks Milvus as 'Unwired (real backend)'"
    )


# ---------------------------------------------------------------------------
# AC6 & AC7: Existing test suites extended to cover ingest-to-search round trip
# ---------------------------------------------------------------------------


def test_port_article_crud_from_file_to_milvus__ac6_milvus_client_test_extended():
    """AC6: test_milvus_client__2.py must include ingest-to-search round-trip coverage."""
    with open(TEST_MILVUS_CLIENT) as f:
        content = f.read()
    has_round_trip = (
        "round_trip" in content
        or "ingest_to_search" in content
        or "round trip" in content.lower()
    )
    assert has_round_trip, (
        "tests/test_milvus_client__2.py has not been extended with ingest-to-search round-trip test"
    )


def test_port_article_crud_from_file_to_milvus__ac7_milvus_schema_test_extended():
    """AC7: test_milvus_schema__3.py must include ingest-to-search round-trip coverage."""
    with open(TEST_MILVUS_SCHEMA) as f:
        content = f.read()
    has_round_trip = (
        "round_trip" in content
        or "ingest_to_search" in content
        or "round trip" in content.lower()
    )
    assert has_round_trip, (
        "tests/test_milvus_schema__3.py has not been extended with ingest-to-search round-trip test"
    )


# ---------------------------------------------------------------------------
# AC8: listArticles, getArticle, deleteArticle are async functions
# ---------------------------------------------------------------------------


def test_port_article_crud_from_file_to_milvus__ac8_functions_are_async():
    """AC8: All three article CRUD functions must be declared as async."""
    with open(COLLECTION_JS) as f:
        src = f.read()
    for fn in ("listArticles", "getArticle", "deleteArticle"):
        assert re.search(rf"export\s+async\s+function\s+{fn}", src), (
            f"{fn} must be declared as 'export async function {fn}'"
        )


# ---------------------------------------------------------------------------
# AC9: E2E test file exists in the coder's test suite
# ---------------------------------------------------------------------------


def test_port_article_crud_from_file_to_milvus__ac9_e2e_test_file_exists():
    """AC9: A new end-to-end test file covering the full CRUD cycle must exist."""
    assert os.path.isfile(E2E_TEST_PATH), (
        f"E2E test file tests/test_article_crud_milvus__33.py not found in coder branch"
    )


def test_port_article_crud_from_file_to_milvus__ac9_e2e_test_covers_delete_then_search():
    """AC9: E2E test must cover the delete → search-confirms-removal step."""
    if not os.path.isfile(E2E_TEST_PATH):
        pytest.skip("E2E test file does not exist — covered by ac9_e2e_test_file_exists")
    with open(E2E_TEST_PATH) as f:
        content = f.read()
    has_delete_then_search = (
        re.search(r"delete.*search|deleteArticle.*search", content, re.DOTALL | re.IGNORECASE)
        or ("deleteArticle" in content and "search" in content.lower())
    )
    assert has_delete_then_search, (
        "E2E test must cover: delete article → search confirms it no longer appears"
    )


# ---------------------------------------------------------------------------
# UAT smoke: UAT server is responding
# ---------------------------------------------------------------------------


def test_port_article_crud_from_file_to_milvus__uat_server_responds(client):
    """Smoke: UAT server at UAT_BASE_URL must respond with HTTP 200."""
    r = client.get("/")
    assert r.status_code == 200
