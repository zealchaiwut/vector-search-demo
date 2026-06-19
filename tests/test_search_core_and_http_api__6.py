"""Tests for issue #6: Add search core and HTTP API endpoints (runs against UAT)"""
import os

import httpx
import pytest

UAT_BASE_URL = os.environ.get("UAT_BASE_URL", "http://localhost:8001")

CODER_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "coder")
)
CORE_SEARCH_PATH = os.path.join(CODER_DIR, "src", "core", "search.js")
SERVER_PATH = os.path.join(CODER_DIR, "src", "server.mjs")

REQUIRED_FIELDS = {"id", "headline", "details", "score", "attachment_url"}


@pytest.fixture
def client():
    with httpx.Client(base_url=UAT_BASE_URL, timeout=10.0) as c:
        yield c


# --- AC1: searchDocuments exists in core and embeds query ---

def test_search_core_and_http_api__searchdocuments_exported_from_core():
    # AC1: searchDocuments exported from src/core/search.js and references embed
    assert os.path.exists(CORE_SEARCH_PATH), f"Core search not found at {CORE_SEARCH_PATH}"
    with open(CORE_SEARCH_PATH) as f:
        src = f.read()
    assert "export function searchDocuments" in src, "searchDocuments not exported from core"
    assert "embed" in src, "searchDocuments does not call embed()"


# --- AC2: ANN search uses COSINE similarity with ef=64 and over-fetches ---

def test_search_core_and_http_api__ef64_and_cosine_in_source():
    # AC2: EF=64 constant and cosine similarity present; slice to EF before collapsing
    with open(CORE_SEARCH_PATH) as f:
        src = f.read()
    assert "EF = 64" in src, "EF constant not set to 64"
    assert "cosineSimilarity" in src or "cosine" in src.lower(), "Cosine similarity not used"
    assert ".slice(0, EF)" in src, "Over-fetch slice to EF not present"


# --- AC3: Collapsing keeps only best-scoring chunk per article id ---

def test_search_core_and_http_api__one_result_per_article_id(client):
    # AC3: no duplicate article ids in results
    r = client.get("/search", params={"q": "semantic embedding vector search", "k": "10"})
    assert r.status_code == 200
    results = r.json()["results"]
    article_ids = [item["id"] for item in results]
    assert len(article_ids) == len(set(article_ids)), f"Duplicate article ids in results: {article_ids}"


# --- AC4: Result shape has required fields with correct constraints ---

def test_search_core_and_http_api__result_shape_all_fields(client):
    # AC4: all required fields present; details ≤240 chars; score rounded; attachment_url correct
    r = client.get("/search", params={"q": "vector search", "k": "3"})
    assert r.status_code == 200
    results = r.json()["results"]
    assert len(results) > 0, "Expected results for 'vector search'"
    for item in results:
        missing = REQUIRED_FIELDS - set(item.keys())
        assert not missing, f"Result missing fields: {missing}"
        assert len(item["details"]) <= 240, f"Details exceeds 240 chars: {len(item['details'])}"
        assert isinstance(item["score"], float), f"Score not float: {type(item['score'])}"
        assert item["score"] == round(item["score"], 4), "Score not rounded to 4dp"
        assert item["attachment_url"] == f"/download/{item['id']}"


# --- AC5: Results ordered descending by score, capped at k ---

def test_search_core_and_http_api__ordered_descending_capped_at_k(client):
    # AC5: scores descending, count ≤ k
    r = client.get("/search", params={"q": "semantic similarity embedding", "k": "3"})
    assert r.status_code == 200
    results = r.json()["results"]
    assert len(results) <= 3, f"Expected ≤3 results for k=3, got {len(results)}"
    scores = [item["score"] for item in results]
    assert scores == sorted(scores, reverse=True), "Results not ordered by descending score"


# --- AC6: GET /search returns shaped JSON array ---

def test_search_core_and_http_api__search_endpoint_returns_json_array(client):
    # AC6: /search returns 200 JSON with results array containing shaped objects
    r = client.get("/search", params={"q": "milvus database", "k": "5"})
    assert r.status_code == 200
    assert "application/json" in r.headers.get("content-type", "")
    data = r.json()
    assert "results" in data and isinstance(data["results"], list)
    assert len(data["results"]) >= 1, "Expected ≥1 result for 'milvus database'"


def test_search_core_and_http_api__search_empty_query_returns_empty_array(client):
    # AC6 edge: empty query returns [] not an error
    r = client.get("/search", params={"q": "zzzmatchnothing999", "k": "5"})
    assert r.status_code == 200
    data = r.json()
    assert data["results"] == [], f"No-match query should return [], got {data['results']}"


# --- AC7: GET /download/:docId streams file with correct headers ---

def test_search_core_and_http_api__download_known_doc_streams_with_headers(client):
    # AC7: known article id returns 200, Content-Disposition: attachment, non-empty body
    r = client.get("/download/article-001")
    assert r.status_code == 200
    cd = r.headers.get("content-disposition", "")
    assert "attachment" in cd, f"Content-Disposition missing 'attachment': {cd!r}"
    assert r.headers.get("content-type"), "Content-Type header missing"
    assert len(r.content) > 0, "Download body is empty"


# --- AC8: GET /download/:docId returns 404 for unknown docId ---

def test_search_core_and_http_api__download_nonexistent_returns_404(client):
    # AC8: unknown doc_id returns HTTP 404
    r = client.get("/download/nonexistent-id-xyz")
    assert r.status_code == 404


# --- AC9: No stub routes in server.mjs ---

def test_search_core_and_http_api__no_stub_logic_in_server():
    # AC9: server.mjs has no leftover stub/TODO patterns; real routes wired
    with open(SERVER_PATH) as f:
        src = f.read()
    for pattern in ["TODO", "stub", "not implemented", "placeholder"]:
        assert pattern.lower() not in src.lower(), f"Stub pattern '{pattern}' found in server.mjs"
    assert "searchDocuments" in src, "/search route must call searchDocuments"
    assert "/download/" in src, "/download/ route must be present"
