/**
 * Minimal HTTP server for vector-search-demo.
 *
 * Endpoints:
 *   GET /search?q=<query>    — returns ranked result cards
 *   GET /download/:articleId — returns the source article as a file download
 *   POST /api/upload-pdf     — upload PDF, extract text, return article JSON
 *   GET /uploads/:filename   — serve uploaded PDF files
 *   GET /                    — serves public/index.html
 *   GET /static/*            — serves files from public/
 */

import { createServer } from "node:http";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { existsSync } from "node:fs";
import { join, extname, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { randomUUID } from "node:crypto";
import { searchDocuments } from "./core/search.js";
import { batchEmbed } from "./data/embedder.js";
import { upsertRows, getArticle, deleteArticle, listArticles, entityCount } from "./data/collection.js";
import { validateArticle, validateArticleId } from "./data/articleValidation.js";
import { extractPdfText } from "./pdf/index.js";
import { mapPdfToArticle } from "./pdf/mapper.js";
import { TesseractOcr } from "./ocr/index.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = join(__dirname, "..");
const PUBLIC_DIR = join(REPO_ROOT, "public");
const ATTACHMENTS_DIR = join(REPO_ROOT, "attachments");
const UPLOADS_DIR = join(REPO_ROOT, "uploads");
const PORT = parseInt(process.env.PORT ?? "3000", 10);

await mkdir(UPLOADS_DIR, { recursive: true });

// ---------------------------------------------------------------------------
// Multipart form-data parser — extracts the first file part
// ---------------------------------------------------------------------------

function parseMultipartFile(body, boundary) {
  const crlf = Buffer.from("\r\n");
  const delimiter = Buffer.from(`\r\n--${boundary}`);
  const firstLine = Buffer.from(`--${boundary}\r\n`);

  let pos = body.indexOf(firstLine);
  if (pos === -1) return null;
  pos += firstLine.length;

  while (pos < body.length) {
    const headerEnd = body.indexOf(Buffer.from("\r\n\r\n"), pos);
    if (headerEnd === -1) break;
    const headers = body.slice(pos, headerEnd).toString("utf-8");
    pos = headerEnd + 4;

    const nextDelim = body.indexOf(delimiter, pos);
    const partData = nextDelim !== -1 ? body.slice(pos, nextDelim) : body.slice(pos);

    const cdMatch = headers.match(/content-disposition:\s*form-data[^;]*(?:;\s*name="([^"]*)")?(?:;\s*filename="([^"]*)")?/i);
    if (cdMatch && cdMatch[2]) {
      return { filename: cdMatch[2], data: partData };
    }

    if (nextDelim === -1) break;
    pos = nextDelim + delimiter.length;
    if (body[pos] === 45 && body[pos + 1] === 45) break; // trailing --
    if (body[pos] === 13 && body[pos + 1] === 10) pos += 2;
  }

  return null;
}

async function search(query, k = 10) {
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
      "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
    });
    res.end();
    return;
  }

  // POST /api/upload-pdf — receive PDF, extract text, return article JSON
  if (req.method === "POST" && pathname === "/api/upload-pdf") {
    const contentType = req.headers["content-type"] ?? "";
    const boundaryMatch = contentType.match(/boundary=([^\s;]+)/);
    if (!boundaryMatch) {
      jsonResponse(res, 400, { error: "Expected multipart/form-data with a boundary" });
      return;
    }
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    const rawBody = Buffer.concat(chunks);
    const file = parseMultipartFile(rawBody, boundaryMatch[1]);
    if (!file) {
      jsonResponse(res, 400, { error: "No PDF file found in request" });
      return;
    }
    const safeName = file.filename.replace(/[^a-zA-Z0-9._-]/g, "_");
    const uniqueName = `${randomUUID()}-${safeName}`;
    const filePath = join(UPLOADS_DIR, uniqueName);
    await writeFile(filePath, file.data);
    try {
      const ocr = new TesseractOcr();
      const text = await extractPdfText(file.data, ocr);
      const attachment_url = `/uploads/${encodeURIComponent(uniqueName)}`;
      const article = mapPdfToArticle(text, { fileName: safeName, attachmentUrl: attachment_url });
      jsonResponse(res, 200, article);
    } catch (err) {
      jsonResponse(res, 422, { error: `Extraction failed: ${err.message ?? String(err)}` });
    }
    return;
  }

  // GET /uploads/:filename — serve stored PDF uploads
  if (req.method === "GET" && pathname.startsWith("/uploads/")) {
    const filename = decodeURIComponent(pathname.slice("/uploads/".length));
    const filePath = join(UPLOADS_DIR, filename);
    if (!filePath.startsWith(UPLOADS_DIR) || !existsSync(filePath)) {
      jsonResponse(res, 404, { error: "Upload not found" });
      return;
    }
    const content = await readFile(filePath);
    res.writeHead(200, {
      "Content-Type": "application/pdf",
      "Content-Length": content.length,
      "Access-Control-Allow-Origin": "*",
    });
    res.end(content);
    return;
  }

  // POST /articles/bulk — create multiple articles from a parsed rows array
  if (req.method === "POST" && pathname === "/articles/bulk") {
    let body = "";
    for await (const chunk of req) body += chunk;
    let payload;
    try {
      payload = JSON.parse(body);
    } catch {
      jsonResponse(res, 400, { error: "Invalid JSON" });
      return;
    }
    const rows = Array.isArray(payload.rows) ? payload.rows : [];

    // Validate all rows first (atomic rejection — nothing persisted if any fail)
    const allErrors = [];
    for (let i = 0; i < rows.length; i++) {
      const row = rows[i];
      const fieldErrors = validateArticle(row.headline, row.details, row.attachment_url);
      for (const e of fieldErrors) {
        allErrors.push({ index: i, field: e.field, reason: e.message });
      }
    }
    if (allErrors.length > 0) {
      jsonResponse(res, 400, { errors: allErrors });
      return;
    }

    // All rows valid — persist all
    let succeeded = 0;
    for (const row of rows) {
      const headline = (row.headline ?? "").trim();
      const details = (row.details ?? "").trim();
      const attachment_url = (row.attachment_url ?? "").trim();
      const id = randomUUID();
      const [{ embedding }] = await batchEmbed([{ details: `${headline} ${details}` }]);
      await upsertRows([{ id: `${id}:0`, headline, details, attachment_url, embedding }]);
      succeeded++;
    }
    jsonResponse(res, 200, {
      total: rows.length,
      succeeded,
      failed: 0,
      errors: [],
    });
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
    const fieldErrors = validateArticle(payload.headline, payload.details, payload.attachment_url);
    if (fieldErrors.length > 0) {
      jsonResponse(res, 400, { error: fieldErrors[0].message, errors: fieldErrors });
      return;
    }
    const headline = (payload.headline ?? "").trim();
    const details = (payload.details ?? "").trim();
    const attachment_url = (payload.attachment_url ?? "").trim();
    const id = randomUUID();
    const [{ embedding }] = await batchEmbed([{ details: `${headline} ${details}` }]);
    await upsertRows([{ id: `${id}:0`, headline, details, attachment_url, embedding }]);
    jsonResponse(res, 201, { id });
    return;
  }

  // GET /articles — list all articles
  if (req.method === "GET" && pathname === "/articles") {
    const articles = await listArticles();
    jsonResponse(res, 200, { articles });
    return;
  }

  // PUT /articles/:id — update an existing article
  if (req.method === "PUT" && pathname.startsWith("/articles/")) {
    const articleId = pathname.slice("/articles/".length);
    if (!articleId) {
      jsonResponse(res, 400, { error: "Article id is required" });
      return;
    }
    const idError = validateArticleId(articleId);
    if (idError) {
      jsonResponse(res, 400, { error: idError });
      return;
    }
    const existing = await getArticle(articleId);
    if (!existing) {
      jsonResponse(res, 404, { error: "Article not found" });
      return;
    }
    let body = "";
    for await (const chunk of req) body += chunk;
    let payload;
    try {
      payload = JSON.parse(body);
    } catch {
      jsonResponse(res, 400, { error: "Invalid JSON" });
      return;
    }
    const fieldErrors = validateArticle(payload.headline, payload.details, payload.attachment_url);
    if (fieldErrors.length > 0) {
      jsonResponse(res, 400, { error: fieldErrors[0].message, errors: fieldErrors });
      return;
    }
    const headline = (payload.headline ?? "").trim();
    const details = (payload.details ?? "").trim();
    const attachment_url = (payload.attachment_url ?? "").trim();
    const [{ embedding }] = await batchEmbed([{ details: `${headline} ${details}` }]);
    await upsertRows([{ id: `${articleId}:0`, headline, details, attachment_url, embedding }]);
    jsonResponse(res, 200, { id: articleId });
    return;
  }

  // DELETE /articles/:id — remove an article
  if (req.method === "DELETE" && pathname.startsWith("/articles/")) {
    const articleId = pathname.slice("/articles/".length);
    if (!articleId) {
      jsonResponse(res, 400, { error: "Article id is required" });
      return;
    }
    const idError = validateArticleId(articleId);
    if (idError) {
      jsonResponse(res, 400, { error: idError });
      return;
    }
    const removed = await deleteArticle(articleId);
    if (!removed) {
      jsonResponse(res, 404, { error: "Article not found" });
      return;
    }
    jsonResponse(res, 200, { id: articleId });
    return;
  }

  // GET /health/integrity — compare article count vs. vector count
  if (req.method === "GET" && pathname === "/health/integrity") {
    const vectorCount = await entityCount();
    const articleCount = (await listArticles()).length;
    if (vectorCount === articleCount) {
      jsonResponse(res, 200, { status: "ok", articleCount, vectorCount });
    } else {
      const delta = Math.abs(vectorCount - articleCount);
      jsonResponse(res, 200, { status: "mismatch", articleCount, vectorCount, delta });
    }
    return;
  }

  // GET /search?q=<query>
  // Result shape: [{ id, headline, details, score, attachment_url, best_passage }]
  if (req.method === "GET" && pathname === "/search") {
    const q = url.searchParams.get("q") ?? "";
    const k = parseInt(url.searchParams.get("k") ?? "10", 10);
    try {
      const results = await search(q, k);
      jsonResponse(res, 200, { results });
    } catch (err) {
      console.error("[server] Search failed unexpectedly:", err?.message ?? err);
      jsonResponse(res, 502, { error: "Search service unavailable" });
    }
    return;
  }

  // GET /download/:articleId
  if (req.method === "GET" && pathname.startsWith("/download/")) {
    const articleId = pathname.slice("/download/".length);
    const filePath = join(ATTACHMENTS_DIR, `${articleId}.txt`);
    if (!existsSync(filePath)) {
      jsonResponse(res, 404, { error: "Attachment not found" });
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
      jsonResponse(res, 404, { error: "Attachment not found" });
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
