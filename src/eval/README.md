# src/eval — Thai Retrieval Evaluation

This directory contains the Thai-language evaluation harness for the vector-search-demo.

## Files

| File | Purpose |
|------|---------|
| `thai_eval_set.json` | Labeled Thai query dataset |
| `run_eval.py` | Python evaluation runner |
| `index.js` | Legacy JS recall-only runner (issue #9) |

---

## Dataset format — `thai_eval_set.json`

A JSON array where each entry is:

```json
{
  "query": "<Thai natural-language query string>",
  "expected": ["<article-id-1>", "<article-id-2>"]
}
```

- **`query`** — A Thai-language search query.
- **`expected`** — One or more article or chunk IDs that should appear in the
  top-k results for this query when the corpus is correctly indexed.

To add a new labeled query, append an entry to `thai_eval_set.json`. No code changes are required.

---

## Metrics

All three metrics are computed at the same `k` (configurable via the `K` env var, default 10).

### Recall@k

The fraction of queries for which at least one expected ID appears in the top-k results.

```
Recall@k = (# queries with ≥1 expected ID in top-k) / (total queries)
```

Range: 0–1. Does not penalize for finding the right document at rank 5 vs rank 1.

### nDCG@k (Normalized Discounted Cumulative Gain)

Rewards finding the correct result at a higher rank.

```
DCG@k  = Σ rel_i / log2(i+2)   for i = 0 .. k-1   (rel_i ∈ {0, 1})
IDCG@k = DCG of the ideal (perfect) ranking
nDCG@k = DCG@k / IDCG@k         (0 when IDCG = 0)
```

A result at rank 1 contributes `1 / log2(2) = 1.0` to DCG; at rank 2, `1 / log2(3) ≈ 0.63`; at rank k, `1 / log2(k+2)`. nDCG is strictly more informative than flat Recall@k.

Range: 0–1.

### MRR (Mean Reciprocal Rank)

The mean of the reciprocal rank of the first relevant result per query.

```
RR(q)  = 1 / rank_of_first_relevant_result   (0 if no relevant result in top-k)
MRR    = mean(RR(q)) over all queries
```

Range: 0–1. MRR = 1.0 means every query found the correct result at rank 1.

---

## Running the eval

```bash
# Against a running local server (default port 8000):
python3 src/eval/run_eval.py

# Configurable:
K=5 RECALL_THRESHOLD=0.7 SEARCH_URL=http://localhost:8080/search python3 src/eval/run_eval.py

# With corpus validation (checks that expected IDs exist before running):
COLLECTION_FILE=/path/to/corpus.json python3 src/eval/run_eval.py
```

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | Recall@k ≥ RECALL_THRESHOLD |
| 1 | Recall@k < RECALL_THRESHOLD, or corpus validation failed |

---

## Corpus validation

Set `COLLECTION_FILE` to a JSON file of the form:

```json
{ "articles": [{ "id": "article-thai-001" }, ...] }
```

The script will exit non-zero with a descriptive error if any `expected` ID in the dataset is not present in the corpus. This guards against stale or mistyped article IDs in the eval data.
