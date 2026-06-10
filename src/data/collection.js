/**
 * File-backed vector collection — simulates a Milvus collection for the demo.
 * Backed by collection.json at the repo root.
 */

import { writeFileSync, readFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const COLLECTION_PATH = join(__dirname, "..", "..", "collection.json");

export function dropCollection() {
  if (existsSync(COLLECTION_PATH)) {
    writeFileSync(COLLECTION_PATH, "[]", "utf8");
  }
}

export function createCollection() {
  writeFileSync(COLLECTION_PATH, "[]", "utf8");
}

export function insertRows(rows) {
  const existing = existsSync(COLLECTION_PATH)
    ? JSON.parse(readFileSync(COLLECTION_PATH, "utf8"))
    : [];
  writeFileSync(COLLECTION_PATH, JSON.stringify([...existing, ...rows]), "utf8");
}

export function entityCount() {
  if (!existsSync(COLLECTION_PATH)) return 0;
  return JSON.parse(readFileSync(COLLECTION_PATH, "utf8")).length;
}
