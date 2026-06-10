/**
 * Minimal HTTP server for vector-search-demo.
 *
 * Endpoints:
 *   GET /search?q=<query>    — returns ranked result cards
 *   GET /download/:docId     — returns the source document as a file download
 *   GET /                    — serves public/index.html
 *   GET /static/*            — serves files from public/
 */

import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { join, extname, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = join(__dirname, "..");
const PUBLIC_DIR = join(REPO_ROOT, "public");
const PORT = parseInt(process.env.PORT ?? "3000", 10);

// ---------------------------------------------------------------------------
// Sample document corpus (demo data — replace with real ingestion pipeline)
// ---------------------------------------------------------------------------

const DOCUMENTS = [
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
// Naive TF-IDF-style scoring (good enough for demo; not real vector search)
// ---------------------------------------------------------------------------

function tokenise(text) {
  return text.toLowerCase().match(/\b[a-z0-9]+\b/g) ?? [];
}

function scoreDocument(doc, queryTokens) {
  const haystack = tokenise(
    [doc.title, doc.content, ...doc.tags].join(" ")
  );
  const haystackSet = new Set(haystack);
  let hits = 0;
  for (const t of queryTokens) {
    if (haystackSet.has(t)) hits++;
  }
  if (queryTokens.length === 0) return 0;
  const raw = hits / queryTokens.length;
  // Apply title-match boost
  const titleTokens = tokenise(doc.title);
  const titleHits = queryTokens.filter((t) => titleTokens.includes(t)).length;
  const boost = titleHits > 0 ? 0.15 : 0;
  return Math.min(1, raw + boost);
}

function search(query, k = 10) {
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

// ---------------------------------------------------------------------------
// Static file helpers
// ---------------------------------------------------------------------------

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css",
  ".js": "application/javascript",
  ".mjs": "application/javascript",
  ".json": "application/json",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".ico": "image/x-icon",
};

async function serveFile(filePath, res) {
  try {
    const content = await readFile(filePath);
    const mime = MIME[extname(filePath)] ?? "application/octet-stream";
    res.writeHead(200, { "Content-Type": mime });
    res.end(content);
  } catch {
    res.writeHead(404, { "Content-Type": "text/plain" });
    res.end("Not found");
  }
}

// ---------------------------------------------------------------------------
// Request handler
// ---------------------------------------------------------------------------

function jsonResponse(res, status, body) {
  const payload = JSON.stringify(body);
  res.writeHead(status, {
    "Content-Type": "application/json",
    "Content-Length": Buffer.byteLength(payload),
    "Access-Control-Allow-Origin": "*",
  });
  res.end(payload);
}

async function handleRequest(req, res) {
  const url = new URL(req.url, `http://localhost:${PORT}`);
  const { pathname } = url;

  // CORS preflight
  if (req.method === "OPTIONS") {
    res.writeHead(204, { "Access-Control-Allow-Origin": "*" });
    res.end();
    return;
  }

  // GET /search?q=<query>
  if (req.method === "GET" && pathname === "/search") {
    const q = url.searchParams.get("q") ?? "";
    const k = parseInt(url.searchParams.get("k") ?? "10", 10);
    const results = search(q, k);
    jsonResponse(res, 200, { results });
    return;
  }

  // GET /download/:docId
  if (req.method === "GET" && pathname.startsWith("/download/")) {
    const doc_id = pathname.slice("/download/".length);
    const doc = DOCUMENTS.find((d) => d.doc_id === doc_id);
    if (!doc) {
      jsonResponse(res, 404, { error: "Document not found" });
      return;
    }
    const content = Buffer.from(`${doc.title}\n\n${doc.content}\n`);
    res.writeHead(200, {
      "Content-Type": "text/plain; charset=utf-8",
      "Content-Disposition": `attachment; filename="${doc_id}.txt"`,
      "Content-Length": content.length,
      "Access-Control-Allow-Origin": "*",
    });
    res.end(content);
    return;
  }

  // GET / → public/index.html
  if (req.method === "GET" && (pathname === "/" || pathname === "/index.html")) {
    await serveFile(join(PUBLIC_DIR, "index.html"), res);
    return;
  }

  // Other static files
  if (req.method === "GET") {
    const filePath = join(PUBLIC_DIR, pathname);
    if (existsSync(filePath)) {
      await serveFile(filePath, res);
      return;
    }
  }

  res.writeHead(404, { "Content-Type": "text/plain" });
  res.end("Not found");
}

// ---------------------------------------------------------------------------
// Start server
// ---------------------------------------------------------------------------

const server = createServer(handleRequest);
server.listen(PORT, () => {
  console.log(`vector-search-demo server running at http://localhost:${PORT}`);
});

export { search, DOCUMENTS };
