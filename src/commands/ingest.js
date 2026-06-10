import { generateDocuments } from "../data/generator.js";
import { chunkDocuments } from "../data/chunker.js";
import { batchEmbed } from "../data/embedder.js";
import { dropCollection, createCollection, insertRows } from "../data/collection.js";
import { writeFileSync, mkdirSync, rmSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = join(__dirname, "..", "..");
const ATTACHMENTS_DIR = join(REPO_ROOT, "attachments");

export function runIngest() {
  // Reset collection from scratch (idempotent)
  dropCollection();
  createCollection();

  // Reset attachments directory
  if (existsSync(ATTACHMENTS_DIR)) {
    rmSync(ATTACHMENTS_DIR, { recursive: true, force: true });
  }
  mkdirSync(ATTACHMENTS_DIR);

  // Generate synthetic documents
  const docs = generateDocuments();

  // Write one attachment file per document
  for (const doc of docs) {
    writeFileSync(
      join(ATTACHMENTS_DIR, `${doc.doc_id}.txt`),
      `${doc.title}\n\n${doc.body}\n`,
      "utf8"
    );
  }

  // Chunk all documents
  const chunks = chunkDocuments(docs);

  // Batch-embed all chunks at once
  const embeddedChunks = batchEmbed(chunks);

  // Build rows for collection insertion
  const rows = embeddedChunks.map((c) => ({
    doc_id: c.doc_id,
    chunk_id: c.chunk_id,
    title: c.title,
    text: c.text,
    attachment_name: c.attachment_name,
    embedding: c.embedding,
  }));

  insertRows(rows);

  process.stdout.write(`${docs.length} docs / ${rows.length} chunks indexed\n`);
}
