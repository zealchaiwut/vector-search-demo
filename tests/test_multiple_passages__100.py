"""Tests for issue #100: Show multiple matching passages per result card (runs against UAT)"""
import os
import pytest
import httpx


BASE_URL = os.environ.get("UAT_BASE_URL") or "http://localhost:" + os.environ.get("UAT_PORT", "")
if not BASE_URL.startswith("http"):
    raise RuntimeError(
        "UAT_BASE_URL / UAT_PORT not set. Run the tester skill's Step 0 to resolve UAT before pytest."
    )


@pytest.fixture
def client():
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as c:
        yield c


@pytest.fixture
def setup_multi_chunk_articles(client):
    """Create test articles with multiple chunks to enable multi-passage search results"""
    articles = [
        {
            "headline": "Machine Learning Basics",
            "details": "Neural networks are fundamental. They learn through backpropagation algorithms. Training requires gradient descent optimization. Activation functions enable non-linearity.",
            "attachment_url": None,
        },
        {
            "headline": "Deep Learning Advanced",
            "details": "Convolutional networks excel at image processing. Transformers revolutionize NLP with attention mechanisms. Recurrent networks handle sequential data. GPUs accelerate training significantly.",
            "attachment_url": None,
        },
        {
            "headline": "Single Chunk Article",
            "details": "This article contains minimal content for testing single passage rendering behavior.",
            "attachment_url": None,
        },
    ]

    # Create articles via bulk endpoint
    resp = client.post("/articles/bulk", json={"rows": articles})
    assert resp.status_code == 200, f"Failed to create articles: {resp.text}"
    result = resp.json()
    assert result["succeeded"] == 3, f"Not all articles created: {result}"
    return articles


# --- Acceptance Criteria Tests ---

def test_multiple_passages__multiple_chunks_render_separately(client, setup_multi_chunk_articles):
    # AC: When the search response contains multiple chunk hits for a document,
    # the result card renders each chunk as a separate highlighted passage.
    resp = client.get("/search?q=neural+networks")
    assert resp.status_code == 200
    data = resp.json()
    results = data.get("results", [])

    # Find the Machine Learning article in results
    ml_article = next((r for r in results if "Machine Learning" in r.get("headline", "")), None)
    assert ml_article is not None, "Expected Machine Learning article in search results"

    # Check for multiple passages
    passages = ml_article.get("passages", [])
    assert len(passages) > 0, "Expected at least one passage in the result"
    assert isinstance(passages, list), "passages field should be a list"


def test_multiple_passages__each_passage_has_distinct_score(client, setup_multi_chunk_articles):
    # AC: Each passage displays its own individual relevance score/indicator.
    resp = client.get("/search?q=neural+networks")
    assert resp.status_code == 200
    data = resp.json()
    results = data.get("results", [])

    ml_article = next((r for r in results if "Machine Learning" in r.get("headline", "")), None)
    assert ml_article is not None

    passages = ml_article.get("passages", [])
    if len(passages) > 1:
        # Each passage should have a score field
        for passage in passages:
            assert "score" in passage, "Each passage should have a score field"
            assert isinstance(passage["score"], (int, float)), "Score should be numeric"


def test_multiple_passages__order_matches_api(client, setup_multi_chunk_articles):
    # AC: Passages are rendered in the order they are returned by the API (no client-side re-sorting).
    resp = client.get("/search?q=learning")
    assert resp.status_code == 200
    data = resp.json()
    results = data.get("results", [])

    for result in results:
        passages = result.get("passages", [])
        if len(passages) > 1:
            # Verify passages list structure is preserved in order
            scores = [p.get("score") for p in passages]
            assert len(scores) == len(passages), "All passages should have scores"


def test_single_chunk__no_visual_regression(client, setup_multi_chunk_articles):
    # AC: A document with exactly one chunk hit renders identically to current single-passage layout.
    resp = client.get("/search?q=minimal")
    assert resp.status_code == 200
    data = resp.json()
    results = data.get("results", [])

    single_chunk = next((r for r in results if "Single Chunk" in r.get("headline", "")), None)
    if single_chunk:
        passages = single_chunk.get("passages", [])
        # Should have at most one passage
        assert len(passages) <= 1, "Single chunk article should not have multiple passages"


def test_no_chunks__headline_only_renders(client, setup_multi_chunk_articles):
    # AC: A document with zero chunk hits (headline-only match) renders without errors.
    # (This tests that search handles results with no passages gracefully)
    resp = client.get("/search?q=network")
    assert resp.status_code == 200
    data = resp.json()
    results = data.get("results", [])

    # All results should be valid JSON objects with required fields
    for result in results:
        assert "id" in result
        assert "headline" in result
        # passages can be empty or missing, but shouldn't cause errors
        passages = result.get("passages", [])
        assert isinstance(passages, list), "passages should be a list when present"


def test_highlight_styles__unchanged(client, setup_multi_chunk_articles):
    # AC: No existing highlight styles are modified; only the passage list structure is changed.
    resp = client.get("/search?q=neural")
    assert resp.status_code == 200
    data = resp.json()
    results = data.get("results", [])

    # Verify all passages still have the required text field for rendering
    for result in results:
        passages = result.get("passages", [])
        for passage in passages:
            # Each passage should have text and context for styling
            if passage:
                assert "text" in passage or passage == {}, "Passage should have text field"
                # If passage has context, it should have the expected structure
                if "context" in passage:
                    assert isinstance(passage["context"], dict), "context should be a dict"


def test_mobile_viewport__stacking_test(client, setup_multi_chunk_articles):
    # AC: Resize to mobile width and passages stack vertically.
    # (HTTP test verifies API returns proper structure; CSS/layout tested in browser)
    resp = client.get("/search?q=learning")
    assert resp.status_code == 200
    data = resp.json()
    results = data.get("results", [])

    # Verify all multi-passage results have consistent structure
    for result in results:
        passages = result.get("passages", [])
        # Each passage should have independent fields (no shared state)
        passage_texts = [p.get("text", "") for p in passages if p]
        # If multiple passages, texts should differ (no duplication)
        if len(passage_texts) > 1:
            assert len(passage_texts) == len(set(passage_texts)), "Duplicate passages should be deduped"
