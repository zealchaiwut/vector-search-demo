#!/usr/bin/env python3
"""
Thai evaluation script for vector-search-demo.

Metric definitions:
  Recall@k  — Fraction of queries where at least one expected ID appears in the
              top-k results.  Range: 0–1.

  nDCG@k    — Normalized Discounted Cumulative Gain.  Rewards ranking the
              correct result higher.  For a result list of length k:
                DCG  = Σ rel_i / log2(i+2)  for i = 0..k-1  (rel_i ∈ {0, 1})
                IDCG = DCG of the ideal ranking (all relevant results first)
                nDCG = DCG / IDCG   (0 when IDCG=0)
              Range: 0–1.  A hit at rank 1 scores higher than the same hit at
              rank k, making nDCG strictly more informative than flat recall.

  MRR       — Mean Reciprocal Rank.  For each query: the reciprocal of the
              rank of the first relevant result in top-k (0 if none).
              MRR = mean(1/rank_first_hit) over all queries.  Range: 0–1.

All three metrics are computed at the same k.

Environment variables:
  SEARCH_URL        HTTP endpoint (default: http://localhost:8000/search)
  K                 Number of top results to consider (default: 10)
  RECALL_THRESHOLD  Minimum recall@k to pass (default: 0.80)
  EVAL_DATASET      Path to the JSON query dataset (default: thai_eval_set.json
                    in the same directory as this script)
  COLLECTION_FILE   Optional path to a corpus JSON file:
                      {"articles": [{"id": "..."}, ...]}
                    When set, the script validates that every expected ID in
                    the dataset exists in the corpus before running queries.
                    Any unknown ID causes a non-zero exit with a clear error.
"""

import json
import math
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

_DIR = os.path.dirname(os.path.abspath(__file__))

SEARCH_URL = os.environ.get("SEARCH_URL", "http://localhost:8000/search")
K = int(os.environ.get("K", "10"))
RECALL_THRESHOLD = float(os.environ.get("RECALL_THRESHOLD", "0.80"))
DATASET_PATH = os.environ.get("EVAL_DATASET", os.path.join(_DIR, "thai_eval_set.json"))
COLLECTION_FILE = os.environ.get("COLLECTION_FILE", "")


# ---------------------------------------------------------------------------
# Metric helpers (importable for unit-testing)
# ---------------------------------------------------------------------------

def compute_ndcg(results: list[str], expected: set[str], k: int) -> float:
    """nDCG@k — normalized Discounted Cumulative Gain at rank k."""
    gains = [1.0 if r in expected else 0.0 for r in results[:k]]
    dcg = sum(g / math.log2(i + 2) for i, g in enumerate(gains))
    # Ideal: all relevant results first
    ideal = sorted(gains, reverse=True)
    idcg = sum(g / math.log2(i + 2) for i, g in enumerate(ideal))
    return dcg / idcg if idcg > 0 else 0.0


def compute_rr(results: list[str], expected: set[str], k: int) -> float:
    """Reciprocal rank of the first relevant result in top-k (0 if not found)."""
    for i, r in enumerate(results[:k]):
        if r in expected:
            return 1.0 / (i + 1)
    return 0.0


# ---------------------------------------------------------------------------
# Search helper
# ---------------------------------------------------------------------------

def search(query: str, k: int) -> list[str] | None:
    """Return article/chunk IDs from the top-k search results, or None on error.

    On any failure (network error, non-200 status, malformed JSON) a WARNING is
    printed to stderr so the caller can distinguish a genuine zero-recall run from
    an infrastructure outage.
    """
    params = urllib.parse.urlencode({"q": query, "k": k})
    url = f"{SEARCH_URL}?{params}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        return [r["id"] for r in data.get("results", []) if r.get("id")]
    except Exception as exc:
        print(f"WARNING: search({query!r}) failed: {exc}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# Corpus validation
# ---------------------------------------------------------------------------

def validate_corpus(entries: list[dict], corpus_ids: set[str]) -> list[str]:
    """Return a list of error strings for expected IDs not found in the corpus."""
    errors = []
    for i, entry in enumerate(entries):
        for eid in entry.get("expected", []):
            if eid not in corpus_ids:
                errors.append(
                    f"Entry {i} (query={entry['query']!r}): "
                    f"expected ID {eid!r} does not exist in the corpus"
                )
    return errors


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    # Load dataset
    with open(DATASET_PATH, encoding="utf-8") as f:
        entries = json.load(f)

    # Corpus validation (optional)
    if COLLECTION_FILE:
        try:
            with open(COLLECTION_FILE, encoding="utf-8") as f:
                corpus_data = json.load(f)
            corpus_ids: set[str] = {a["id"] for a in corpus_data.get("articles", []) if a.get("id")}
        except (OSError, json.JSONDecodeError, KeyError) as exc:
            print(f"ERROR: Cannot read corpus file {COLLECTION_FILE!r}: {exc}", file=sys.stderr)
            sys.exit(1)

        errors = validate_corpus(entries, corpus_ids)
        if errors:
            print("ERROR: Dataset references article/chunk IDs not found in corpus:", file=sys.stderr)
            for err in errors:
                print(f"  {err}", file=sys.stderr)
            sys.exit(1)

    n = len(entries)
    hits_recall: list[bool] = []
    ndcg_scores: list[float] = []
    rr_scores: list[float] = []
    error_count = 0

    for entry in entries:
        query = entry["query"]
        expected = set(entry["expected"])
        raw = search(query, K)
        if raw is None:
            error_count += 1
            results: list[str] = []
        else:
            results = raw

        hit = bool(expected & set(results[:K]))
        hits_recall.append(hit)
        ndcg_scores.append(compute_ndcg(results, expected, K))
        rr_scores.append(compute_rr(results, expected, K))

        label = "HIT " if hit else "MISS"
        got_str = ", ".join(results[:K]) if results else "(none)"
        exp_str = ", ".join(sorted(expected))
        print(f"[{label}]  query={query!r}  expected=[{exp_str}]  got=[{got_str}]")

    if n > 0 and error_count == n:
        print(
            f"ERROR: All {n} search quer{'y' if n == 1 else 'ies'} failed — "
            f"is the search endpoint reachable? (SEARCH_URL={SEARCH_URL})",
            file=sys.stderr,
        )
        sys.exit(1)

    recall = sum(hits_recall) / n if n else 0.0
    ndcg = sum(ndcg_scores) / n if n else 0.0
    mrr = sum(rr_scores) / n if n else 0.0

    print()
    print(f"Recall@{K}:  {recall:.4f}  ({sum(hits_recall)}/{n} queries hit)")
    print(f"nDCG@{K}:    {ndcg:.4f}")
    print(f"MRR@{K}:     {mrr:.4f}")
    print()

    # Legacy single-recall lines for backwards compatibility with issue #101 tests
    print(f"recall@1:  n/a (use Recall@{K} above)")
    print(f"recall@5:  n/a (use Recall@{K} above)")
    print(f"recall@10: {recall:.2f}  ({sum(hits_recall)}/{n})")
    print()

    if recall < RECALL_THRESHOLD:
        print(f"FAIL: Recall@{K} {recall:.4f} < threshold {RECALL_THRESHOLD:.2f}")
        sys.exit(1)

    print(f"PASS: Recall@{K} {recall:.4f} >= threshold {RECALL_THRESHOLD:.2f}")
    sys.exit(0)


if __name__ == "__main__":
    main()
