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
import { searchDocuments, DOCUMENTS } from "./core/search.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = join(__dirname, "..");
const PUBLIC_DIR = join(REPO_ROOT, "public");
const PORT = parseInt(process.env.PORT ?? "3000", 10);

function search(query, k = 10) {
  return searchDocuments(query, k);
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
  // Result shape: [{ doc_id, title, snippet, score, attachment_name, download_url }]
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

export { search, searchDocuments, DOCUMENTS };
