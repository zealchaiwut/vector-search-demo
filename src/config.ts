import { readFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

// Minimal .env loader (no dependency): populate process.env from the repo-root
// .env file for any keys not already set in the real environment.
// config.{ts,js} lives directly in src/ (→ dist/), one level below the repo root.
const __dirname = dirname(fileURLToPath(import.meta.url));
const ENV_PATH = join(__dirname, "..", ".env");
if (existsSync(ENV_PATH)) {
  for (const line of readFileSync(ENV_PATH, "utf8").split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const eq = trimmed.indexOf("=");
    if (eq === -1) continue;
    const key = trimmed.slice(0, eq).trim();
    const value = trimmed.slice(eq + 1).trim().replace(/^["']|["']$/g, "");
    if (key && process.env[key] === undefined) process.env[key] = value;
  }
}

export const config = {
  port: parseInt(process.env.PORT ?? "8000", 10),
  milvusAddress: process.env.MILVUS_ADDRESS ?? "localhost:19530",
  collectionName: process.env.COLLECTION_NAME ?? "documents",
  embeddingModel: process.env.EMBEDDING_MODEL ?? "Xenova/all-MiniLM-L6-v2",
  dim: parseInt(process.env.DIM ?? "384", 10),
};
