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

interface PassageContext {
  before: string;
  after: string;
}

interface Passage {
  text: string;
  start_offset: number;
  end_offset: number;
  context: PassageContext;
  score: number;
}

/**
 * A single pipeline stage entry in the debug explain block.
 * Only present on results when the search request includes `debug: true`.
 */
interface ExplainStage {
  /** Pipeline stage name: one of 'dense', 'lexical', 'rrf', 'rerank'. */
  stage: "dense" | "lexical" | "rrf" | "rerank";
  /** Score assigned to this result at this stage. */
  score: number;
  /** 1-indexed rank of this result at this stage. */
  rank: number;
  /** Change in rank compared to the immediately prior stage (0 for the first stage). */
  rankDelta: number;
  /** Wall-clock time in milliseconds consumed by this stage. */
  latencyMs: number;
}

interface SearchResult {
  id: string;
  article_id?: string;
  chunk_index?: number;
  headline: string;
  details: string;
  text?: string;
  score: number;
  attachment_url: string | null;
  /** "external" for http(s) URLs, "local" for /download/ paths, null when no attachment */
  attachment_url_type: "external" | "local" | null;
  best_passage: Passage;
  /** Matching chunk passage(s) for this row. */
  passages: Passage[];
  chunks: { text: string; score: number; chunk_index?: number }[];
  /**
   * Debug explain block — only present when the request includes `debug: true`.
   * Contains one entry per pipeline stage that ran; stages that did not run are omitted.
   */
  explain?: ExplainStage[];
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
      const results = (await searchDocuments(
        q,
        Number.isFinite(k) ? k : 10,
      )) as SearchResult[];
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
