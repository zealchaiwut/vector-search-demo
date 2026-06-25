import { resolveBackend, logActiveBackend, getStore } from "../store/factory.js";
import { batchEmbed } from "../data/embedder.js";
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = join(__dirname, "..", "..");
const COLLECTION_PATH = join(REPO_ROOT, "collection.json");

function parseArgs(argv) {
  const args = argv.slice(2);
  return {
    recreate: args.includes("--recreate") || args.includes("--force"),
    help: args.includes("--help") || args.includes("-h"),
  };
}

function printHelp() {
  process.stdout.write(
    "Usage: commander re-embed [options]\n\n" +
      "Re-encode all stored documents with the currently configured EMBEDDING_MODEL.\n\n" +
      "Options:\n" +
      "  --recreate    Drop and recreate the storage table with the new vector dimension.\n" +
      "                Required when switching to a model with a different output dimension.\n" +
      "                For postgres: drops the articles table, recreates with the new dim,\n" +
      "                then re-embeds all data. See SCHEMA.md for migration details.\n" +
      "  --force       Alias for --recreate.\n" +
      "  --help, -h    Show this help message.\n"
  );
}

async function reEmbedMock() {
  if (!existsSync(COLLECTION_PATH)) {
    process.stdout.write("Nothing to re-embed: collection.json not found\n");
    return 0;
  }
  const rows = JSON.parse(readFileSync(COLLECTION_PATH, "utf8"));
  if (!Array.isArray(rows) || rows.length === 0) {
    process.stdout.write("Nothing to re-embed: collection is empty\n");
    return 0;
  }

  const updated = await batchEmbed(rows);
  writeFileSync(COLLECTION_PATH, JSON.stringify(updated), "utf8");
  return updated.length;
}

async function reEmbedPostgres(recreate) {
  const { getPgStore } = await import("../store/PgVectorStore.js");
  const store = getPgStore();
  await store.migrate();

  if (recreate) {
    process.stdout.write("[re-embed] --recreate: saving data and rebuilding table with new dimension…\n");
    const savedRows = await store.recreateWithNewDimension();
    if (savedRows.length === 0) {
      process.stdout.write("Nothing to re-embed: articles table was empty\n");
      return 0;
    }
    const rows = savedRows.map((r) => ({
      id: r.id,
      headline: r.headline,
      details: r.details,
      attachment_url: r.attachment_url,
    }));
    const updated = await batchEmbed(rows);
    await store.upsert(updated);
    return updated.length;
  }

  // Normal re-embed (no dimension change)
  await store.checkSchemaCompatibility();

  const result = await store._query(
    "SELECT id, article_id, chunk_index, headline, details, attachment_url FROM articles ORDER BY article_id, chunk_index"
  );
  const rows = result.rows.map((r) => ({
    id: r.id,
    article_id: r.article_id,
    chunk_index: r.chunk_index,
    headline: r.headline,
    details: r.details,
    attachment_url: r.attachment_url,
  }));
  if (rows.length === 0) {
    process.stdout.write("Nothing to re-embed: articles table is empty\n");
    return 0;
  }
  const updated = await batchEmbed(rows);
  await store.upsert(updated);
  return updated.length;
}

export async function runReEmbed(argv = process.argv) {
  const opts = parseArgs(argv);

  if (opts.help) {
    printHelp();
    return;
  }

  const backend = resolveBackend();
  logActiveBackend(backend);

  const MODEL = process.env.EMBEDDING_MODEL ?? "Xenova/multilingual-e5-small";

  let count = 0;
  if (backend === "mock") {
    count = await reEmbedMock();
  } else if (backend === "postgres") {
    count = await reEmbedPostgres(opts.recreate);
  } else {
    process.stderr.write(
      `re-embed: backend '${backend}' is not supported for in-place re-embedding. ` +
        "Run ingest to rebuild all embeddings.\n"
    );
    process.exit(1);
  }

  process.stdout.write(`${count} chunks re-embedded with ${MODEL}\n`);
}
