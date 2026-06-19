/**
 * Recall@k evaluation script for vector-search-demo.
 *
 * Configurable via env vars:
 *   SEARCH_URL        HTTP endpoint for the search API  (default: derived from PORT, else :7070)
 *   PORT              Port the server listens on        (default: 7070)
 *   K                 Number of top results to consider (default: 5)
 *   RECALL_THRESHOLD  Minimum pass fraction 0.0–1.0    (default: 0.8)
 *
 * Exit code: 0 when recall@k >= threshold, non-zero otherwise.
 */

const PORT = process.env.PORT ?? "7070";
const SEARCH_URL = process.env.SEARCH_URL ?? `http://localhost:${PORT}/search`;
const K = parseInt(process.env.K ?? "5", 10);
const RECALL_THRESHOLD = parseFloat(process.env.RECALL_THRESHOLD ?? "0.8");

// Hardcoded query fixtures — each maps a natural-language query to one or more
// expected article id values that should appear in the top-K results when the
// collection is fully ingested.
const QUERIES = [
  {
    "query": "what is vector search",
    "expected": ["article-001"],
  },
  {
    "query": "semantic similarity and embedding models",
    "expected": ["article-002"],
  },
  {
    "query": "approximate nearest neighbor algorithms",
    "expected": ["article-003"],
  },
  {
    "query": "milvus vector database setup",
    "expected": ["article-004"],
  },
  {
    "query": "transformer sentence embeddings MiniLM",
    "expected": ["article-005"],
  },
  {
    "query": "end to end semantic search pipeline",
    "expected": ["article-006"],
  },
];

async function searchDocuments(query, k) {
  const response = await fetch(SEARCH_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ q: query, k }),
  });
  if (!response.ok) {
    throw new Error(`Search API returned HTTP ${response.status}`);
  }
  const data = await response.json();
  return Array.isArray(data.results) ? data.results : [];
}

async function main() {
  let hits = 0;

  for (const { query, expected } of QUERIES) {
    let returnedIds = [];
    let isHit = false;

    try {
      const results = await searchDocuments(query, K);
      returnedIds = results.map((r) => r.id ?? "").filter(Boolean);
      isHit = expected.some((id) => returnedIds.includes(id));
    } catch (err) {
      // Search backend unavailable or errored — treat as miss
      returnedIds = [];
      isHit = false;
    }

    if (isHit) hits++;

    const label = isHit ? "HIT " : "MISS";
    const expectedStr = expected.join(", ");
    const gotStr = returnedIds.length > 0 ? returnedIds.slice(0, K).join(", ") : "(none)";
    console.log(`[${label}]  query="${query}"  expected=[${expectedStr}]  got=[${gotStr}]`);
  }

  const total = QUERIES.length;
  const recall = total > 0 ? hits / total : 0;
  console.log(`\nRecall@${K}: ${recall.toFixed(2)} (${hits}/${total} queries passed)`);

  if (recall < RECALL_THRESHOLD) {
    console.log(`FAIL: recall@${K} ${recall.toFixed(2)} < threshold ${RECALL_THRESHOLD}`);
    process.exit(1);
  }

  console.log(`PASS: recall@${K} ${recall.toFixed(2)} >= threshold ${RECALL_THRESHOLD}`);
  process.exit(0);
}

main();
