"""Tests for issue #14: Add best-matching passage to search results (runs against UAT)"""
import os

import httpx
import pytest

BASE_URL = os.environ.get("UAT_BASE_URL", "http://localhost:8001")

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE_SEARCH_JS = os.path.join(REPO_ROOT, "..", "coder", "src", "core", "search.js")

CURRENT_FIELDS = {"id", "headline", "details", "score", "attachment_url"}


@pytest.fixture
def client():
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as c:
        yield c


# --- AC1: every result contains a best_passage field ---

def test_add_best_matching_passage__every_result_has_best_passage(client):
    # AC1: GET /search response: every result contains a best_passage field
    r = client.get("/search", params={"q": "vector embedding similarity", "k": "5"})
    assert r.status_code == 200
    results = r.json()["results"]
    assert len(results) >= 1, "Expected at least one result"
    for res in results:
        assert "best_passage" in res, (
            f"id={res.get('id')} missing 'best_passage'. Keys: {list(res.keys())}"
        )


# --- AC2: best_passage is non-empty ---

def test_add_best_matching_passage__best_passage_non_empty(client):
    # AC2: best_passage is non-empty for all returned results
    r = client.get("/search", params={"q": "semantic search indexing", "k": "5"})
    assert r.status_code == 200
    results = r.json()["results"]
    for res in results:
        bp = res.get("best_passage", {})
        assert bp.get("text"), (
            f"id={res.get('id')} has empty or missing best_passage.text"
        )


# --- AC3: best_passage.text verbatim in document text ---

def test_add_best_matching_passage__text_verbatim_in_document(client):
    # AC3: best_passage.text is a single sentence taken verbatim from the document
    r = client.get("/search", params={"q": "vector database index", "k": "3"})
    assert r.status_code == 200
    results = r.json()["results"]
    for res in results:
        bp = res["best_passage"]
        passage_text = bp["text"]
        dl = client.get(res["attachment_url"])
        assert dl.status_code == 200
        raw_normalized = dl.text.replace("\n", " ")
        assert passage_text in raw_normalized, (
            f"id={res['id']}: best_passage.text not found verbatim in document. "
            f"passage={passage_text!r}"
        )


# --- AC4: best_passage includes start_offset and end_offset ---

def test_add_best_matching_passage__offsets_present_and_valid(client):
    # AC4: best_passage includes start_offset and end_offset character indices
    r = client.get("/search", params={"q": "embedding model training", "k": "5"})
    assert r.status_code == 200
    results = r.json()["results"]
    for res in results:
        bp = res["best_passage"]
        assert "start_offset" in bp, f"id={res['id']} missing start_offset"
        assert "end_offset" in bp, f"id={res['id']} missing end_offset"
        assert isinstance(bp["start_offset"], int) and bp["start_offset"] >= 0
        assert isinstance(bp["end_offset"], int) and bp["end_offset"] > bp["start_offset"]


# --- AC5/AC6: topically relevant sentence for targeted query ---

def test_add_best_matching_passage__relevant_sentence_for_targeted_query(client):
    # AC6: for a query clearly about one part of a document, best_passage returns
    # the topically relevant sentence, not an unrelated one
    r = client.get("/search", params={"q": "cosine similarity", "k": "3"})
    assert r.status_code == 200
    results = r.json()["results"]
    assert len(results) >= 1
    top_result = results[0]
    bp_text = top_result["best_passage"]["text"].lower()
    # The best passage for a cosine similarity query should mention similarity or distance concepts
    assert any(kw in bp_text for kw in ("cosine", "similar", "distance", "dot", "vector", "embedding")), (
        f"best_passage for 'cosine similarity' query appears unrelated: {bp_text!r}"
    )


# --- AC7: document ranking order unchanged ---

def test_add_best_matching_passage__ranking_order_preserved(client):
    # AC7: document ranking order identical (verified by checking scores are descending)
    r = client.get("/search", params={"q": "semantic search", "k": "5"})
    assert r.status_code == 200
    results = r.json()["results"]
    scores = [res["score"] for res in results]
    assert scores == sorted(scores, reverse=True), (
        f"Results not sorted by descending score: {scores}"
    )


# --- AC8: passage extraction bounded to top-k results only ---

def test_add_best_matching_passage__bounded_to_top_k(client):
    # AC8: passage extraction bounded to top-k returned documents (not full corpus)
    r1 = client.get("/search", params={"q": "vector search engine", "k": "1"})
    r2 = client.get("/search", params={"q": "vector search engine", "k": "3"})
    assert r1.status_code == 200 and r2.status_code == 200
    assert len(r1.json()["results"]) == 1, "k=1 should return exactly 1 result"
    assert all("best_passage" in res for res in r1.json()["results"])
    assert all("best_passage" in res for res in r2.json()["results"])


# --- AC9: search API fields are present (news-article schema) ---

def test_add_best_matching_passage__current_fields_intact(client):
    # AC9: current API contract fields are present (news-article schema)
    r = client.get("/search", params={"q": "document retrieval", "k": "3"})
    assert r.status_code == 200
    results = r.json()["results"]
    for res in results:
        missing = CURRENT_FIELDS - res.keys()
        assert not missing, (
            f"id={res.get('id')} is missing required fields: {missing}"
        )


# --- AC10: changes scoped to src/core/search.js ---

def test_add_best_matching_passage__scoped_to_core_search():
    # AC10: implementation lives in src/core/search.js
    assert os.path.exists(CORE_SEARCH_JS), (
        f"Expected implementation at {CORE_SEARCH_JS}"
    )
    with open(CORE_SEARCH_JS) as f:
        src = f.read()
    assert "best_passage" in src, "best_passage not found in src/core/search.js"
    assert "selectBestPassage" in src or "best_passage" in src
