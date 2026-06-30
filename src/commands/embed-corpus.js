/**
 * embed-corpus — embed all existing chunks under a named model.
 *
 * Usage: commander embed-corpus --model <name>
 *
 * Reads all chunks from the active backend (mock: collection.json; postgres:
 * articles table), embeds each chunk's text using the specified model, and
 * stores the resulting vectors in the per-model store (mock: chunk_embeddings.json;
 * postgres: chunk_embeddings table). Idempotent: re-running for the same model
 * does not duplicate rows — existing entries are overwritten.
 */

import { resolveModel } from "../embeddings/model-registry.js";
import { resolveBackend, logActiveBackend } from "../store/factory.js";
import { getMultiModelStore } from "../store/MultiModelStore.js";
import { readFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = join(__dirname, "..", "..");
const COLLECTION_PATH = join(REPO_ROOT, "collection.json");

function parseArgs(argv) {
  let modelName = null;
  let help = false;

  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--model" && i + 1 < argv.length) {
      modelName = argv[i + 1];
      i++;
    } else if (argv[i] === "--help" || argv[i] === "-h") {
      help = true;
    }
  }

  return { modelName, help };
}

function printHelp() {
  process.stdout.write(
    "Usage: commander embed-corpus --model <name>\n\n" +
      "Embed all stored chunks under the specified model and store vectors in\n" +
      "the per-model embedding table (chunk_embeddings). Idempotent.\n\n" +
      "Options:\n" +
      "  --model <name>  Embedding model to use (required). Must be a registered\n" +
      "                  model name (e.g. BAAI/bge-m3, multilingual-e5-large).\n" +
      "  --help, -h      Show this help message.\n\n" +
      "Supported models: multilingual-e5-small, multilingual-e5-base,\n" +
      "                  multilingual-e5-large, BAAI/bge-m3\n"
  );
}

async function createEmbedderForModel(modelName) {
  const info = resolveModel(modelName);
  const { pipeline } = await import("@xenova/transformers");
  const pipe = await pipeline("feature-extraction", info.xenovaId);

  return {
    dim: info.dim,
    async embed(texts) {
      const output = await pipe(texts, { pooling: "mean", normalize: true });
      return output.tolist();
    },
  };
}

function loadMockChunks() {
  if (!existsSync(COLLECTION_PATH)) return [];
  try {
    const rows = JSON.parse(readFileSync(COLLECTION_PATH, "utf8"));
    return Array.isArray(rows) ? rows : [];
  } catch {
    return [];
  }
}

async function embedCorpusMock(modelName) {
  const chunks = loadMockChunks();
  if (chunks.length === 0) {
    process.stdout.write("Nothing to embed: collection is empty\n");
    return 0;
  }

  process.stdout.write(`[embed-corpus] Loading model ${modelName}…\n`);
  const embedder = await createEmbedderForModel(modelName);
  const store = getMultiModelStore();

  const BATCH = 32;
  let total = 0;

  for (let i = 0; i < chunks.length; i += BATCH) {
    const batch = chunks.slice(i, i + BATCH);
    const texts = batch.map((c) => `passage: ${c.details}`);
    const vectors = await embedder.embed(texts);

    for (let j = 0; j < batch.length; j++) {
      await store.upsert(batch[j].id, modelName, vectors[j], embedder.dim);
    }
    total += batch.length;
    process.stdout.write(`[embed-corpus] ${total}/${chunks.length} chunks processed\n`);
  }

  return total;
}

async function embedCorpusPostgres(modelName) {
  const { getPgStore } = await import("../store/PgVectorStore.js");
  const pgStore = getPgStore();
  await pgStore.migrate();

  const result = await pgStore._query(
    "SELECT id, article_id, chunk_index, details FROM articles ORDER BY article_id, chunk_index"
  );
  const chunks = result.rows;

  if (chunks.length === 0) {
    process.stdout.write("Nothing to embed: articles table is empty\n");
    return 0;
  }

  process.stdout.write(`[embed-corpus] Loading model ${modelName}…\n`);
  const embedder = await createEmbedderForModel(modelName);

  const BATCH = 32;
  let total = 0;

  for (let i = 0; i < chunks.length; i += BATCH) {
    const batch = chunks.slice(i, i + BATCH);
    const texts = batch.map((c) => `passage: ${c.details}`);
    const vectors = await embedder.embed(texts);

    for (let j = 0; j < batch.length; j++) {
      await pgStore.upsertChunkEmbedding(
        batch[j].id,
        modelName,
        vectors[j],
        embedder.dim
      );
    }
    total += batch.length;
    process.stdout.write(`[embed-corpus] ${total}/${chunks.length} chunks processed\n`);
  }

  return total;
}

export async function runEmbedCorpus(argv = []) {
  const opts = parseArgs(argv);

  if (opts.help) {
    printHelp();
    return;
  }

  if (!opts.modelName) {
    process.stderr.write(
      "Error: --model <name> is required.\n" +
        "Run `commander embed-corpus --help` for usage.\n"
    );
    process.exit(1);
  }

  // Validate model early for a clear error before doing any work.
  resolveModel(opts.modelName);

  const backend = resolveBackend();
  logActiveBackend(backend);

  let count = 0;

  if (backend === "mock") {
    count = await embedCorpusMock(opts.modelName);
  } else if (backend === "postgres") {
    count = await embedCorpusPostgres(opts.modelName);
  } else {
    process.stderr.write(
      `embed-corpus: backend '${backend}' is not supported. Use mock or postgres.\n`
    );
    process.exit(1);
  }

  process.stdout.write(
    `${count} chunks embedded with ${opts.modelName} and stored in chunk_embeddings.\n`
  );
}
