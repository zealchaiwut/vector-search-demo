#!/usr/bin/env python3
"""
Thai evaluation script for vector-search-demo.

Loads thai_eval_set.json, runs each query against the search API, and reports
recall@1, recall@5, and recall@10. Exits with a non-zero code when recall@10
falls below the configured threshold.

Environment variables:
  SEARCH_URL        HTTP endpoint (default: http://localhost:7070/search)
  RECALL_THRESHOLD  Minimum recall@10 pass fraction 0.0–1.0 (default: 0.80)
"""

import json
import os
import sys
import urllib.request
import urllib.parse
import urllib.error

_DIR = os.path.dirname(os.path.abspath(__file__))

SEARCH_URL = os.environ.get("SEARCH_URL", "http://localhost:7070/search")
RECALL_THRESHOLD = float(os.environ.get("RECALL_THRESHOLD", "0.80"))
DATASET_PATH = os.path.join(_DIR, "thai_eval_set.json")


def search(query: str, k: int) -> list[str]:
    """Return article IDs from the top-k search results."""
    params = urllib.parse.urlencode({"q": query, "k": k})
    url = f"{SEARCH_URL}?{params}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        return [r["id"] for r in data.get("results", []) if r.get("id")]
    except Exception:
        return []


def recall_at(hits_at_k: list[bool]) -> float:
    if not hits_at_k:
        return 0.0
    return sum(hits_at_k) / len(hits_at_k)


def main() -> None:
    with open(DATASET_PATH, encoding="utf-8") as f:
        entries = json.load(f)

    n = len(entries)
    hits1 = []
    hits5 = []
    hits10 = []

    for entry in entries:
        query = entry["query"]
        expected = set(entry["expected"])
        results = search(query, 10)
        top1 = set(results[:1])
        top5 = set(results[:5])
        top10 = set(results[:10])

        hit1 = bool(expected & top1)
        hit5 = bool(expected & top5)
        hit10 = bool(expected & top10)
        hits1.append(hit1)
        hits5.append(hit5)
        hits10.append(hit10)

        label1 = "HIT " if hit1 else "MISS"
        label10 = "HIT " if hit10 else "MISS"
        got_str = ", ".join(results[:10]) if results else "(none)"
        exp_str = ", ".join(sorted(expected))
        print(f"[{label10}]  query=\"{query}\"  expected=[{exp_str}]  @1={label1.strip()}  got=[{got_str}]")

    r1 = recall_at(hits1)
    r5 = recall_at(hits5)
    r10 = recall_at(hits10)

    print()
    print(f"recall@1:  {r1:.2f}  ({sum(hits1)}/{n})")
    print(f"recall@5:  {r5:.2f}  ({sum(hits5)}/{n})")
    print(f"recall@10: {r10:.2f}  ({sum(hits10)}/{n})")
    print()

    if r10 < RECALL_THRESHOLD:
        print(f"FAIL: recall@10 {r10:.2f} is below threshold {RECALL_THRESHOLD:.2f}")
        sys.exit(1)

    print(f"PASS: recall@10 {r10:.2f} >= threshold {RECALL_THRESHOLD:.2f}")
    sys.exit(0)


if __name__ == "__main__":
    main()
