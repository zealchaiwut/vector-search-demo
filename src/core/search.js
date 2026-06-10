/**
 * Core search logic for vector-search-demo.
 * Pure functions — no HTTP, no side-effects.
 */

export const DOCUMENTS = [
  {
    doc_id: "doc-001",
    title: "Introduction to Vector Search",
    content:
      "Vector search finds similar items by comparing high-dimensional numerical vectors. " +
      "Unlike keyword search, it captures semantic meaning using embedding models.",
    snippet:
      "Vector search finds similar items by comparing high-dimensional numerical vectors, " +
      "capturing semantic meaning using embedding models.",
    tags: ["vector", "search", "embedding", "semantic"],
  },
  {
    doc_id: "doc-002",
    title: "Semantic Similarity and Embedding Models",
    content:
      "Embedding models transform text into dense vector representations that preserve " +
      "semantic relationships. Cosine similarity measures the angle between two vectors.",
    snippet:
      "Embedding models transform text into dense vector representations that preserve " +
      "semantic relationships between words and sentences.",
    tags: ["semantic", "similarity", "embedding", "cosine"],
  },
  {
    doc_id: "doc-003",
    title: "Approximate Nearest Neighbor Algorithms",
    content:
      "ANN algorithms like HNSW and IVF-Flat enable fast approximate nearest-neighbour " +
      "lookups in high-dimensional spaces, trading a small accuracy loss for large speed gains.",
    snippet:
      "ANN algorithms like HNSW and IVF-Flat enable fast nearest-neighbour lookups " +
      "in high-dimensional vector spaces with minimal accuracy loss.",
    tags: ["ann", "hnsw", "ivf", "nearest-neighbor", "approximate"],
  },
  {
    doc_id: "doc-004",
    title: "Milvus Vector Database Setup",
    content:
      "Milvus is an open-source vector database designed for high-performance similarity search. " +
      "It supports multiple index types and can scale to billions of vectors.",
    snippet:
      "Milvus is an open-source vector database for high-performance similarity search, " +
      "supporting multiple index types and billion-scale vector collections.",
    tags: ["milvus", "database", "vector", "setup", "index"],
  },
  {
    doc_id: "doc-005",
    title: "Transformer Sentence Embeddings with MiniLM",
    content:
      "Sentence-Transformers and the MiniLM model family produce compact, high-quality sentence " +
      "embeddings at low computational cost. MiniLM-L6-v2 is a popular choice for semantic search.",
    snippet:
      "Sentence-Transformers with MiniLM produce compact, high-quality sentence embeddings. " +
      "MiniLM-L6-v2 is a popular choice for efficient semantic search.",
    tags: ["transformer", "minilm", "sentence-embedding", "sbert"],
  },
  {
    doc_id: "doc-006",
    title: "End-to-End Semantic Search Pipeline",
    content:
      "A full semantic search pipeline ingests documents, generates embeddings, stores vectors " +
      "in an index, and retrieves the top-k most similar results at query time.",
    snippet:
      "A full semantic search pipeline ingests documents, generates embeddings, stores vectors " +
      "in an index, and retrieves top-k similar results at query time.",
    tags: ["pipeline", "semantic", "search", "end-to-end", "retrieval"],
  },
];

function tokenise(text) {
  return text.toLowerCase().match(/\b[a-z0-9]+\b/g) ?? [];
}

function scoreDocument(doc, queryTokens) {
  const haystack = tokenise([doc.title, doc.content, ...doc.tags].join(" "));
  const haystackSet = new Set(haystack);
  let hits = 0;
  for (const t of queryTokens) {
    if (haystackSet.has(t)) hits++;
  }
  if (queryTokens.length === 0) return 0;
  const raw = hits / queryTokens.length;
  const titleTokens = tokenise(doc.title);
  const titleHits = queryTokens.filter((t) => titleTokens.includes(t)).length;
  const boost = titleHits > 0 ? 0.15 : 0;
  return Math.min(1, raw + boost);
}

export function searchDocuments(query, k = 10) {
  const queryTokens = tokenise(query);
  if (queryTokens.length === 0) return [];
  const scored = DOCUMENTS.map((doc) => ({
    doc_id: doc.doc_id,
    title: doc.title,
    snippet: doc.snippet,
    score: parseFloat(scoreDocument(doc, queryTokens).toFixed(4)),
  }));
  return scored
    .filter((r) => r.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, k);
}
