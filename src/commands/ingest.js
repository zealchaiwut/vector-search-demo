import { generateDocuments } from "../data/generator.js";
import { chunkDocuments } from "../data/chunker.js";
import { batchEmbed } from "../data/embedder.js";
import { dropCollection, createCollection, upsertRows } from "../data/collection.js";
import { writeFileSync, mkdirSync, rmSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = join(__dirname, "..", "..");
const ATTACHMENTS_DIR = join(REPO_ROOT, "attachments");

export async function runIngest() {
  // Reset collection from scratch (idempotent)
  dropCollection();
  createCollection();

  // Reset attachments directory
  if (existsSync(ATTACHMENTS_DIR)) {
    rmSync(ATTACHMENTS_DIR, { recursive: true, force: true });
  }
  mkdirSync(ATTACHMENTS_DIR);

  // Generate news articles
  const articles = generateDocuments();

  // Write one attachment file per article (named by article id)
  for (const article of articles) {
    writeFileSync(
      join(ATTACHMENTS_DIR, `${article.id}.txt`),
      `${article.headline}\n\n${article.details}\n`,
      "utf8"
    );
  }

  // Chunk all articles
  const chunks = chunkDocuments(articles);

  // Batch-embed all chunks at once
  const embeddedChunks = await batchEmbed(chunks);

  // Build rows for collection upsert
  const rows = embeddedChunks.map((c) => ({
    id: c.id,
    headline: c.headline,
    details: c.details,
    attachment_url: c.attachment_url,
    embedding: c.embedding,
  }));

  upsertRows(rows);

  process.stdout.write(`${articles.length} docs / ${rows.length} chunks indexed\n`);
}
