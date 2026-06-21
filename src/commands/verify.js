import { readdirSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { resolveBackend, logActiveBackend, getStore } from "../store/factory.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = join(__dirname, "..", "..");

function getRegisteredArticleIds() {
  const dir = process.env.VERIFY_ATTACHMENTS_DIR || join(REPO_ROOT, "attachments");
  if (!existsSync(dir)) return [];
  return readdirSync(dir)
    .filter((f) => f.endsWith(".txt"))
    .map((f) => f.replace(/\.txt$/, ""));
}

export async function runVerify() {
  const backend = resolveBackend();
  logActiveBackend(backend);
  const store = await getStore(backend);

  const registeredIds = getRegisteredArticleIds();
  const chunks = await store.listChunks();

  const byArticle = new Map();
  for (const chunk of chunks) {
    const articleId = chunk.article_id || chunk.id.split(":")[0];
    if (!byArticle.has(articleId)) byArticle.set(articleId, []);
    byArticle.get(articleId).push(chunk);
  }

  const articlesWithNoChunks = registeredIds.filter(
    (id) => !byArticle.has(id) || byArticle.get(id).length === 0
  );

  const chunksWithNullEmbedding = chunks.filter(
    (c) =>
      c.embedding === null ||
      c.embedding === undefined ||
      (Array.isArray(c.embedding) && c.embedding.length === 0)
  );

  if (articlesWithNoChunks.length === 0 && chunksWithNullEmbedding.length === 0) {
    process.stdout.write(
      `OK: ${registeredIds.length} articles, ${chunks.length} chunks, all embeddings present\n`
    );
    process.exit(0);
    return;
  }

  if (articlesWithNoChunks.length > 0) {
    process.stdout.write(`MISSING CHUNKS for articles:\n`);
    for (const id of articlesWithNoChunks) {
      process.stdout.write(`  ${id}\n`);
    }
  }

  if (chunksWithNullEmbedding.length > 0) {
    process.stdout.write(`NULL EMBEDDING for chunks:\n`);
    for (const chunk of chunksWithNullEmbedding) {
      process.stdout.write(`  ${chunk.id}\n`);
    }
  }

  process.exit(1);
  return;
}
