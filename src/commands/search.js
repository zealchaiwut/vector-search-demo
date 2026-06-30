import {
  resolveBackend,
  logActiveBackend,
  getStore,
} from "../store/factory.js";
import { resolveModel } from "../embeddings/model-registry.js";
import { getMultiModelStore } from "../store/MultiModelStore.js";
import { readFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const COLLECTION_PATH = join(__dirname, "..", "..", "collection.json");

function parseArgs(argv) {
  // Positional: first non-flag arg is the query
  // Flags: -k <number>, --model <name>
  let query = null;
  let k = 10;
  let modelName = null;

  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "-k" && i + 1 < argv.length) {
      k = parseInt(argv[i + 1], 10);
      i++;
    } else if (argv[i] === "--model" && i + 1 < argv.length) {
      modelName = argv[i + 1];
      i++;
    } else if (!argv[i].startsWith("-")) {
      query = argv[i];
    }
  }

  return { query, k, modelName };
}

function loadMockRows() {
  if (!existsSync(COLLECTION_PATH)) return [];
  try {
    const rows = JSON.parse(readFileSync(COLLECTION_PATH, "utf8"));
    return Array.isArray(rows) ? rows : [];
  } catch {
    return [];
  }
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

async function searchWithModel(query, k, modelName, backend) {
  // Validate model — throws with a clear message for unregistered names.
  resolveModel(modelName);

  if (backend === "mock") {
    const embedder = await createEmbedderForModel(modelName);
    const [queryVector] = await embedder.embed([`query: ${query}`]);
    const articleRows = loadMockRows();
    const store = getMultiModelStore();
    return store.search(queryVector, modelName, k, articleRows);
  }

  if (backend === "postgres") {
    const embedder = await createEmbedderForModel(modelName);
    const [queryVector] = await embedder.embed([`query: ${query}`]);
    const { getPgStore } = await import("../store/PgVectorStore.js");
    const pgStore = getPgStore();
    return pgStore.searchByModel(queryVector, modelName, k);
  }

  process.stderr.write(
    `search --model: backend '${backend}' does not support model-targeted search.\n`
  );
  process.exit(1);
}

export async function runSearch(argv) {
  const { query, k, modelName } = parseArgs(argv);

  if (!query || query.trim() === "") {
    process.stderr.write(
      "Usage: commander search <query> [-k <number>] [--model <name>]\nError: query is required\n",
    );
    process.exit(1);
  }

  const backend = resolveBackend();
  logActiveBackend(backend);

  let results;

  if (modelName) {
    results = await searchWithModel(query, k, modelName, backend);
  } else {
    const store = await getStore(backend);
    results = await store.search(query, k);
  }

  if (results.length === 0) {
    process.stdout.write("No results found\n");
    return;
  }

  for (let i = 0; i < results.length; i++) {
    const r = results[i];
    const rank = i + 1;
    process.stdout.write(
      `\n--- Result ---\n` +
        `Rank:       ${rank}\n` +
        `Headline:   ${r.headline}\n` +
        `ID:         ${r.id}\n` +
        `Score:      ${r.score}\n` +
        `URL:        ${r.attachment_url}\n`,
    );
  }
  process.stdout.write("\n");
}
