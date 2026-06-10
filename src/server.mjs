/**
 * Minimal HTTP server for vector-search-demo.
 *
 * Endpoints:
 *   GET /search?q=<query>    — returns ranked result cards
 *   GET /download/:articleId — returns the source article as a file download
 *   GET /                    — serves public/index.html
 *   GET /static/*            — serves files from public/
 */

import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { join, extname, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { randomUUID } from "node:crypto";
import { searchDocuments } from "./core/search.js";
import { batchEmbed } from "./data/embedder.js";
import { upsertRows } from "./data/collection.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = join(__dirname, "..");
const PUBLIC_DIR = join(REPO_ROOT, "public");
const ATTACHMENTS_DIR = join(REPO_ROOT, "attachments");
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
    res.writeHead(204, {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
    });
    res.end();
    return;
  }

  // POST /articles — create a new article
  if (req.method === "POST" && pathname === "/articles") {
    let body = "";
    for await (const chunk of req) body += chunk;
    let payload;
    try {
      payload = JSON.parse(body);
    } catch {
      jsonResponse(res, 400, { error: "Invalid JSON" });
      return;
    }
    const headline = (payload.headline ?? "").trim();
    const details = (payload.details ?? "").trim();
    const attachment_url = (payload.attachment_url ?? "").trim();
    if (!headline || !details) {
      jsonResponse(res, 400, { error: "headline and details are required" });
      return;
    }
    const id = randomUUID();
    const [{ embedding }] = batchEmbed([{ details: `${headline} ${details}` }]);
    upsertRows([{ id: `${id}:0`, headline, details, attachment_url, embedding }]);
    jsonResponse(res, 201, { id });
    return;
  }

  // GET /search?q=<query>
  // Result shape: [{ id, headline, details, score, attachment_url, best_passage }]
  if (req.method === "GET" && pathname === "/search") {
    const q = url.searchParams.get("q") ?? "";
    const k = parseInt(url.searchParams.get("k") ?? "10", 10);
    const results = search(q, k);
    jsonResponse(res, 200, { results });
    return;
  }

  // GET /download/:articleId
  if (req.method === "GET" && pathname.startsWith("/download/")) {
    const articleId = pathname.slice("/download/".length);
    const filePath = join(ATTACHMENTS_DIR, `${articleId}.txt`);
    if (!existsSync(filePath)) {
      jsonResponse(res, 404, { error: "Document not found" });
      return;
    }
    try {
      const content = await readFile(filePath);
      res.writeHead(200, {
        "Content-Type": "text/plain; charset=utf-8",
        "Content-Disposition": `attachment; filename="${articleId}.txt"`,
        "Content-Length": content.length,
        "Access-Control-Allow-Origin": "*",
      });
      res.end(content);
    } catch {
      jsonResponse(res, 404, { error: "Document not found" });
    }
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

export { search, searchDocuments };
