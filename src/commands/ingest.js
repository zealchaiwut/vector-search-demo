import { generateDocuments } from "../data/generator.js";
import { chunkDocuments } from "../data/chunker.js";
import { batchEmbed } from "../data/embedder.js";
import { writeFileSync, mkdirSync, rmSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { resolveBackend, logActiveBackend, getStore } from "../store/factory.js";
import { normalise } from "../text/normalise.js";
import { defaultRetrievalConfig } from "../config/retrieval.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = join(__dirname, "..", "..");
const ATTACHMENTS_DIR = join(REPO_ROOT, "attachments");

export async function runIngest() {
  const backend = resolveBackend();
  logActiveBackend(backend);
  const store = await getStore(backend);

  // Reset collection from scratch (idempotent)
  await store.dropCollection();
  await store.createCollection();

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

  const { textNormalisationEnabled } = defaultRetrievalConfig();

  // Chunk all articles
  const chunks = chunkDocuments(articles);

  // Normalise chunk text before embedding (shared path with query-time normalisation)
  const normalisedChunks = chunks.map((c) => ({
    ...c,
    headline: normalise(c.headline, textNormalisationEnabled),
    details: normalise(c.details, textNormalisationEnabled),
  }));

  // Batch-embed all chunks at once
  const embeddedChunks = await batchEmbed(normalisedChunks);

  // Build rows for collection upsert
  const rows = embeddedChunks.map((c) => ({
    id: c.id,
    headline: c.headline,
    details: c.details,
    attachment_url: c.attachment_url,
    embedding: c.embedding,
  }));

  await store.upsertRows(rows);

  process.stdout.write(`${articles.length} docs / ${rows.length} chunks indexed\n`);
}
