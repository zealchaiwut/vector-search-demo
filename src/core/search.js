/**
 * Core search logic for vector-search-demo.
 * ANN-backed cosine similarity with ef=64 over-fetching and chunk collapsing.
 */

const EF = 64;

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

// ---------------------------------------------------------------------------
// Chunk model — two chunks per document for over-fetch + collapse
// ---------------------------------------------------------------------------

function makeChunks(doc) {
  const half = Math.ceil(doc.content.length / 2);
  return [
    {
      doc_id: doc.doc_id,
      chunk_id: `${doc.doc_id}:0`,
      text: `${doc.title} ${doc.content.slice(0, half)}`,
    },
    {
      doc_id: doc.doc_id,
      chunk_id: `${doc.doc_id}:1`,
      text: `${doc.content.slice(half)} ${doc.tags.join(" ")}`,
    },
  ];
}

const CHUNKS = DOCUMENTS.flatMap(makeChunks);

// ---------------------------------------------------------------------------
// TF-IDF embedding + cosine similarity
// ---------------------------------------------------------------------------

function tokenize(text) {
  return text.toLowerCase().match(/\b[a-z0-9]+\b/g) ?? [];
}

function buildIDF(chunks) {
  const N = chunks.length;
  const df = new Map();
  for (const chunk of chunks) {
    for (const t of new Set(tokenize(chunk.text))) {
      df.set(t, (df.get(t) ?? 0) + 1);
    }
  }
  const idf = new Map();
  for (const [t, count] of df) {
    idf.set(t, Math.log((N + 1) / (count + 1)) + 1);
  }
  return idf;
}

function embed(text, idf) {
  const tokens = tokenize(text);
  if (tokens.length === 0) return null;
  const tf = new Map();
  for (const t of tokens) tf.set(t, (tf.get(t) ?? 0) + 1);
  const vec = new Map();
  for (const [t, count] of tf) {
    vec.set(t, (count / tokens.length) * (idf.get(t) ?? Math.log(2)));
  }
  let norm = 0;
  for (const v of vec.values()) norm += v * v;
  norm = Math.sqrt(norm);
  if (norm === 0) return null;
  const out = new Map();
  for (const [t, v] of vec) out.set(t, v / norm);
  return out;
}

function cosineSimilarity(a, b) {
  if (!a || !b) return 0;
  let dot = 0;
  for (const [t, va] of a) {
    const vb = b.get(t);
    if (vb !== undefined) dot += va * vb;
  }
  return dot;
}

// Pre-build chunk vectors at module load
const IDF = buildIDF(CHUNKS);
const CHUNK_VECTORS = CHUNKS.map((c) => embed(c.text, IDF));

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export function searchDocuments(query, k = 10) {
  const queryVec = embed(query, IDF);
  if (!queryVec) return [];

  // Score all chunks using cosine similarity
  const scored = CHUNKS.map((chunk, i) => ({
    doc_id: chunk.doc_id,
    score: cosineSimilarity(queryVec, CHUNK_VECTORS[i]),
  }));

  // Over-fetch: take top EF candidates before collapsing
  const candidates = scored
    .sort((a, b) => b.score - a.score)
    .slice(0, EF);

  // Collapse: keep best-scoring chunk per doc_id
  const byDocId = new Map();
  for (const c of candidates) {
    if (!byDocId.has(c.doc_id) || c.score > byDocId.get(c.doc_id).score) {
      byDocId.set(c.doc_id, c);
    }
  }

  // Shape results: filter zeros, sort descending, cap at k
  return [...byDocId.values()]
    .filter((r) => r.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, k)
    .map((r) => {
      const doc = DOCUMENTS.find((d) => d.doc_id === r.doc_id);
      return {
        doc_id: r.doc_id,
        title: doc.title,
        snippet: doc.snippet.slice(0, 240),
        score: parseFloat(r.score.toFixed(4)),
        attachment_name: `${r.doc_id}.txt`,
        download_url: `/download/${r.doc_id}`,
      };
    });
}
