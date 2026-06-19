# src/eval — Thai Evaluation Set

This directory contains the Thai-language recall evaluation harness.

## Files

| File | Purpose |
|------|---------|
| `thai_eval_set.json` | Thai query dataset (≥10 queries, each mapped to expected article IDs) |
| `run_eval.py` | Python eval script — runs all queries and reports recall@1/5/10 |
| `index.js` | Legacy JS recall@k script (English queries, configurable k) |

## Dataset schema — `thai_eval_set.json`

The file is a JSON array of objects. Each object has exactly two fields:

```json
{
  "query": "<Thai-language natural-language query>",
  "expected": ["<article-id>", ...]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `query` | string | A Thai-language search query (must contain Thai Unicode characters U+0E00–U+0E7F) |
| `expected` | string[] | One or more article IDs that should appear in the top-10 search results for this query |

Article IDs match the `id` field returned by the `/search` API endpoint (e.g. `article-thai-001`). Chunk suffixes (`:0`, `:1`) are **not** used in the eval set — the search API collapses chunks to article IDs before returning results.

## Running the eval

```bash
python src/eval/run_eval.py
```

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `SEARCH_URL` | `http://localhost:7070/search` | Search API endpoint |
| `RECALL_THRESHOLD` | `0.80` | Minimum recall@10 for a passing run (0.0–1.0) |

The script prints per-query HIT/MISS results followed by recall@1, recall@5, and recall@10 summaries. It exits with code 1 when recall@10 falls below the threshold.

## Interpreting results

- **recall@k** — fraction of queries where at least one expected article appears in the top-k results.
- A recall@10 ≥ 0.80 is the default pass threshold.
- Lower recall on a baseline (non-multilingual) corpus confirms the eval set is sensitive to the multilingual embedding changes.
