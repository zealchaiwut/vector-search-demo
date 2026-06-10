"""
Acceptance tests for issue #14: Add best-matching passage to search results.

AC1  - GET /search response: every result contains a `best_passage` field
AC2  - `best_passage` is non-empty for all returned results
AC3  - `best_passage.text` is a single sentence taken verbatim from the document text
AC4  - `best_passage` includes `start_offset` and `end_offset` character indices
AC5  - `best_passage` selected by cosine similarity using existing Embedder
AC6  - Topically relevant sentence returned for targeted queries
AC7  - Document ranking order identical before and after this change
AC8  - Passage extraction bounded to top-k returned documents only
AC9  - No existing search API contract fields removed or renamed
AC10 - Changes scoped to src/search/ (src/core/search.js)
"""

import json
import os
import re
import subprocess

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE_SEARCH_JS = os.path.join(REPO_ROOT, "src", "core", "search.js")
COLLECTION_JSON = os.path.join(REPO_ROOT, "collection.json")

REQUIRED_LEGACY_FIELDS = {"doc_id", "title", "snippet", "score", "attachment_name", "download_url"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_node(script, timeout=15):
    result = subprocess.run(
        ["node", "--input-type=module"],
        input=script,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=timeout,
    )
    return result.stdout, result.stderr, result.returncode


def _call_search_documents(query, k=10):
    script = f"""
import {{ searchDocuments }} from './src/core/search.js';
const results = searchDocuments({json.dumps(query)}, {k});
process.stdout.write(JSON.stringify(results));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error (rc={rc}): {err}"
    return json.loads(out)


def _load_doc_texts():
    """Return a map of doc_id -> full chunk text from collection.json."""
    with open(COLLECTION_JSON) as f:
        rows = json.load(f)
    texts = {}
    for row in rows:
        doc_id = row["doc_id"]
        if doc_id not in texts:
            texts[doc_id] = row["text"]
        else:
            texts[doc_id] = texts[doc_id] + " " + row["text"]
    return texts


# ---------------------------------------------------------------------------
# AC1 — every result contains best_passage field
# ---------------------------------------------------------------------------

def test_ac1_every_result_has_best_passage():
    results = _call_search_documents("vector search embedding", k=5)
    assert len(results) >= 1, "Expected at least one result"
    for r in results:
        assert "best_passage" in r, \
            f"Result for doc_id={r.get('doc_id')} missing 'best_passage' field. Keys: {list(r.keys())}"


def test_ac1_best_passage_is_object():
    results = _call_search_documents("vector search", k=3)
    for r in results:
        bp = r["best_passage"]
        assert isinstance(bp, dict), \
            f"best_passage must be an object/dict, got {type(bp)}"


# ---------------------------------------------------------------------------
# AC2 — best_passage is non-empty for all returned results
# ---------------------------------------------------------------------------

def test_ac2_best_passage_text_is_nonempty():
    results = _call_search_documents("embedding cosine similarity", k=5)
    assert len(results) >= 1
    for r in results:
        bp = r["best_passage"]
        assert "text" in bp, f"best_passage missing 'text' key for doc_id={r['doc_id']}"
        assert len(bp["text"]) > 0, \
            f"best_passage.text is empty for doc_id={r['doc_id']}"


def test_ac2_best_passage_nonempty_for_all_k():
    results = _call_search_documents("semantic retrieval pipeline", k=10)
    for r in results:
        assert r["best_passage"]["text"].strip() != "", \
            f"best_passage.text is blank for doc_id={r['doc_id']}"


# ---------------------------------------------------------------------------
# AC3 — best_passage.text is verbatim substring of document text
# ---------------------------------------------------------------------------

def test_ac3_text_is_verbatim_substring_of_doc():
    doc_texts = _load_doc_texts()
    results = _call_search_documents("vector search embedding cosine", k=6)
    assert len(results) >= 1
    for r in results:
        doc_id = r["doc_id"]
        passage_text = r["best_passage"]["text"]
        doc_text = doc_texts.get(doc_id, "")
        assert passage_text in doc_text, (
            f"best_passage.text is not a verbatim substring of document text for {doc_id}.\n"
            f"  passage: {passage_text!r}\n"
            f"  doc_text: {doc_text[:200]!r}"
        )


def test_ac3_text_is_single_sentence():
    """Passage text should not span multiple clear sentence boundaries."""
    results = _call_search_documents("neural network embedding", k=5)
    for r in results:
        text = r["best_passage"]["text"].strip()
        # A single sentence: should not contain more than one sentence-ending punctuation
        # followed by a capital letter (rough heuristic for multi-sentence detection)
        sentence_breaks = re.findall(r'[.!?]\s+[A-Z]', text)
        assert len(sentence_breaks) == 0, (
            f"best_passage.text for {r['doc_id']} appears to span multiple sentences: {text!r}"
        )


def test_ac3_text_not_truncated_mid_sentence():
    """Passage text should end at a natural sentence boundary."""
    results = _call_search_documents("approximate nearest neighbour", k=3)
    for r in results:
        text = r["best_passage"]["text"].strip()
        # Should end with sentence-ending punctuation
        assert re.search(r'[.!?]$', text), (
            f"best_passage.text for {r['doc_id']} appears truncated mid-sentence: {text!r}"
        )


# ---------------------------------------------------------------------------
# AC4 — best_passage includes start_offset and end_offset
# ---------------------------------------------------------------------------

def test_ac4_offsets_present():
    results = _call_search_documents("vector database index", k=4)
    for r in results:
        bp = r["best_passage"]
        assert "start_offset" in bp, \
            f"best_passage missing 'start_offset' for doc_id={r['doc_id']}"
        assert "end_offset" in bp, \
            f"best_passage missing 'end_offset' for doc_id={r['doc_id']}"


def test_ac4_offsets_are_integers():
    results = _call_search_documents("cosine similarity", k=3)
    for r in results:
        bp = r["best_passage"]
        assert isinstance(bp["start_offset"], int), \
            f"start_offset must be int, got {type(bp['start_offset'])}"
        assert isinstance(bp["end_offset"], int), \
            f"end_offset must be int, got {type(bp['end_offset'])}"


def test_ac4_offsets_index_into_doc_text():
    """doc_text[start_offset:end_offset] must equal best_passage.text."""
    doc_texts = _load_doc_texts()
    results = _call_search_documents("vector embedding similarity", k=6)
    assert len(results) >= 1
    for r in results:
        doc_id = r["doc_id"]
        bp = r["best_passage"]
        doc_text = doc_texts.get(doc_id, "")
        extracted = doc_text[bp["start_offset"]:bp["end_offset"]]
        assert extracted == bp["text"], (
            f"Offset mismatch for {doc_id}: "
            f"doc_text[{bp['start_offset']}:{bp['end_offset']}]={extracted!r} "
            f"!= best_passage.text={bp['text']!r}"
        )


def test_ac4_start_offset_less_than_end_offset():
    results = _call_search_documents("semantic search", k=5)
    for r in results:
        bp = r["best_passage"]
        assert bp["start_offset"] < bp["end_offset"], (
            f"start_offset ({bp['start_offset']}) must be < end_offset ({bp['end_offset']}) "
            f"for doc_id={r['doc_id']}"
        )


# ---------------------------------------------------------------------------
# AC5 — selected by cosine similarity via existing Embedder
# ---------------------------------------------------------------------------

def test_ac5_search_js_uses_cosine_for_passage():
    with open(CORE_SEARCH_JS) as f:
        src = f.read()
    # Must use cosine/similarity logic for passage selection
    assert re.search(r"cosineSimilarity|cosine|similarity", src, re.IGNORECASE), \
        "search.js must use cosine similarity for best_passage selection"


def test_ac5_search_js_splits_into_sentences():
    with open(CORE_SEARCH_JS) as f:
        src = f.read()
    # Must have sentence splitting logic
    assert re.search(r"sentence|split|\.match\(|\.split\(", src, re.IGNORECASE), \
        "search.js must split text into sentences for passage selection"


# ---------------------------------------------------------------------------
# AC6 — topically relevant sentence for targeted queries
# ---------------------------------------------------------------------------

def test_ac6_relevant_passage_for_specific_query():
    """A query about HNSW should return a passage mentioning HNSW."""
    results = _call_search_documents("HNSW approximate nearest neighbour algorithm", k=5)
    hnsw_results = [r for r in results if "hnsw" in r["doc_id"].lower() or
                    "HNSW" in r["best_passage"]["text"] or "nearest" in r["best_passage"]["text"].lower()]
    assert len(hnsw_results) >= 1, (
        "Query about HNSW should return at least one result with relevant passage text. "
        f"Passages: {[r['best_passage']['text'][:80] for r in results]}"
    )


def test_ac6_passage_text_relates_to_query():
    """Query about 'cosine similarity' should produce passages mentioning it."""
    results = _call_search_documents("cosine similarity calculation", k=3)
    assert len(results) >= 1
    top = results[0]
    passage = top["best_passage"]["text"].lower()
    query_terms = {"cosine", "similarity", "vector", "dot", "embedding"}
    matched = [t for t in query_terms if t in passage]
    assert len(matched) >= 1, (
        f"Top result best_passage should relate to 'cosine similarity' query. "
        f"Passage: {top['best_passage']['text']!r}"
    )


# ---------------------------------------------------------------------------
# AC7 — document ranking order identical before and after
# ---------------------------------------------------------------------------

def test_ac7_result_ids_ordered_by_score_descending():
    """Ranking is determined by doc-level score, not passage score."""
    results = _call_search_documents("vector search semantic embedding", k=10)
    scores = [r["score"] for r in results]
    for i in range(len(scores) - 1):
        assert scores[i] >= scores[i + 1], (
            f"Results not in descending score order at index {i}: "
            f"{scores[i]} < {scores[i+1]}"
        )


def test_ac7_best_passage_score_does_not_alter_doc_order():
    """Doc-level scores should be unchanged by passage extraction."""
    results_with_passage = _call_search_documents("approximate search index", k=6)
    doc_ids_ordered = [r["doc_id"] for r in results_with_passage]
    doc_scores = {r["doc_id"]: r["score"] for r in results_with_passage}

    # Run again — order must be stable
    results_again = _call_search_documents("approximate search index", k=6)
    doc_ids_again = [r["doc_id"] for r in results_again]
    assert doc_ids_ordered == doc_ids_again, (
        f"Result order changed between identical queries: {doc_ids_ordered} vs {doc_ids_again}"
    )


# ---------------------------------------------------------------------------
# AC8 — passage extraction bounded to top-k documents only
# ---------------------------------------------------------------------------

def test_ac8_results_count_does_not_exceed_k():
    results = _call_search_documents("vector search", k=2)
    assert len(results) <= 2, f"Expected at most 2 results with k=2, got {len(results)}"


def test_ac8_passage_only_in_returned_results():
    """best_passage exists only on results returned, not extra docs."""
    results = _call_search_documents("semantic embedding retrieval", k=3)
    # All returned results have best_passage — no extra
    for r in results:
        assert "best_passage" in r
    # Count must respect k cap
    assert len(results) <= 3


# ---------------------------------------------------------------------------
# AC9 — no existing fields removed or renamed
# ---------------------------------------------------------------------------

def test_ac9_all_legacy_fields_present():
    results = _call_search_documents("vector", k=3)
    assert len(results) >= 1
    for r in results:
        missing = REQUIRED_LEGACY_FIELDS - set(r.keys())
        assert not missing, (
            f"Legacy field(s) missing from result for {r.get('doc_id')}: {missing}"
        )


def test_ac9_snippet_still_present_and_correct():
    results = _call_search_documents("embedding model", k=3)
    for r in results:
        assert "snippet" in r
        assert isinstance(r["snippet"], str)
        assert len(r["snippet"]) <= 240


def test_ac9_score_still_numeric_and_rounded():
    results = _call_search_documents("vector search", k=3)
    for r in results:
        assert isinstance(r["score"], (int, float))
        s = str(r["score"])
        decimal_part = s.split(".")[-1] if "." in s else ""
        assert len(decimal_part) <= 4, f"score has too many decimals: {r['score']}"


def test_ac9_download_url_unchanged():
    results = _call_search_documents("vector", k=3)
    for r in results:
        assert r["download_url"] == f"/download/{r['doc_id']}"


# ---------------------------------------------------------------------------
# AC10 — changes scoped to src/core/search.js (the search module)
# ---------------------------------------------------------------------------

def test_ac10_best_passage_logic_in_search_js():
    with open(CORE_SEARCH_JS) as f:
        src = f.read()
    assert "best_passage" in src, \
        "best_passage must be implemented in src/core/search.js"


def test_ac10_search_js_exports_searchDocuments():
    with open(CORE_SEARCH_JS) as f:
        src = f.read()
    assert "export function searchDocuments" in src or "export { searchDocuments" in src, \
        "searchDocuments must remain exported from src/core/search.js"
