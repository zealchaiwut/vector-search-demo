import { readFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { resolveBackend, logActiveBackend, getStore } from "../store/factory.js";
import { chunkDocuments } from "../data/chunker.js";
import { batchEmbed } from "../data/embedder.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = join(__dirname, "..", "..");

function readAttachmentDetails(articleId, fallbackDetails) {
  const dir = process.env.RECHUNK_ATTACHMENTS_DIR || join(REPO_ROOT, "attachments");
  const attachPath = join(dir, `${articleId}.txt`);
  if (!existsSync(attachPath)) return fallbackDetails;
  const content = readFileSync(attachPath, "utf8");
  const sep = content.indexOf("\n\n");
  return sep >= 0 ? content.slice(sep + 2).trim() : content.trim();
}

export async function runRechunk() {
  const backend = resolveBackend();
  logActiveBackend(backend);
  const store = await getStore(backend);

  const articles = await store.listArticles();
  if (articles.length === 0) {
    process.stdout.write("Nothing to rechunk: corpus is empty\n");
    return;
  }

  const errors = [];

  for (const article of articles) {
    try {
      const details = readAttachmentDetails(article.id, article.details);
      const fullArticle = {
        id: article.id,
        headline: article.headline,
        details,
        attachment_url: article.attachment_url,
      };

      await store.deleteArticle(article.id);

      const chunks = chunkDocuments([fullArticle]);
      if (chunks.length === 0) {
        throw new Error("no chunks produced (empty body)");
      }

      const embedded = await batchEmbed(chunks);

      const nullCount = embedded.filter(
        (c) => !c.embedding || (Array.isArray(c.embedding) && c.embedding.length === 0)
      ).length;
      if (nullCount > 0) {
        throw new Error(`${nullCount} chunk(s) received null embeddings`);
      }

      await store.upsertRows(
        embedded.map((c) => ({
          id: c.id,
          headline: c.headline,
          details: c.details,
          attachment_url: c.attachment_url,
          embedding: c.embedding,
        }))
      );
    } catch (err) {
      errors.push(`article ${article.id}: ${err.message}`);
    }
  }

  if (errors.length > 0) {
    process.stderr.write(`rechunk: ${errors.length} article(s) failed:\n`);
    for (const e of errors) {
      process.stderr.write(`  ${e}\n`);
    }
    process.exit(1);
  }

  process.stdout.write(
    `${articles.length} articles rechunked with current chunk settings\n`
  );
}
