import Fastify from "fastify";
import { readFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { config } from "../config.js";
import { searchDocuments } from "../core/search.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const PUBLIC_DIR = join(__dirname, "..", "..", "public");
const ATTACHMENTS_DIR = join(__dirname, "..", "..", "attachments");

interface SearchResult {
  id: string;
  headline: string;
  details: string;
  score: number;
  attachment_url: string;
  best_passage: { text: string; start_offset: number; end_offset: number };
}

export async function createServer() {
  const app = Fastify({ logger: false });

  app.get("/health", async () => {
    return { status: "ok" };
  });

  // GET /search?q=<query>&k=<n> → { results: [...] }
  app.get<{ Querystring: { q?: string; k?: string } }>(
    "/search",
    async (req, reply) => {
      const q = (req.query.q ?? "").trim();
      const k = parseInt(req.query.k ?? "10", 10);
      if (!q) {
        return reply.send({ results: [] as SearchResult[] });
      }
      const results: SearchResult[] = await searchDocuments(q, Number.isFinite(k) ? k : 10);
      return reply.send({ results });
    }
  );

  // GET /download/:docId → the ingested source file as an attachment.
  // Fastify auto-registers a HEAD route for this GET, so `curl -I` works too.
  app.get<{ Params: { docId: string } }>(
    "/download/:docId",
    async (req, reply) => {
      const docId = req.params.docId;
      const filePath = join(ATTACHMENTS_DIR, `${docId}.txt`);
      if (!existsSync(filePath)) {
        return reply.code(404).send({ error: "Document not found" });
      }
      const content = await readFile(filePath);
      return reply
        .type("text/plain; charset=utf-8")
        .header("Content-Disposition", `attachment; filename="${docId}.txt"`)
        .send(content);
    }
  );

  app.get("/", async (_req, reply) => {
    const html = await readFile(join(PUBLIC_DIR, "index.html"), "utf-8");
    reply.type("text/html").send(html);
  });

  return app;
}

export async function startServer() {
  const app = await createServer();
  await app.listen({ port: config.port, host: "0.0.0.0" });
  console.log(`Server running at http://localhost:${config.port}`);
}
