/**
 * File-backed vector collection — simulates a Milvus collection for the demo.
 * Backed by collection.json at the repo root.
 * Upserts by the row's `id` field to prevent duplicates on re-ingest.
 */

import { writeFileSync, readFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const COLLECTION_PATH = join(__dirname, "..", "..", "collection.json");

function load() {
  if (!existsSync(COLLECTION_PATH)) return [];
  try {
    const rows = JSON.parse(readFileSync(COLLECTION_PATH, "utf8"));
    return Array.isArray(rows) ? rows : [];
  } catch {
    return [];
  }
}

function persist(rows) {
  writeFileSync(COLLECTION_PATH, JSON.stringify(rows), "utf8");
}

export function dropCollection() {
  if (existsSync(COLLECTION_PATH)) {
    writeFileSync(COLLECTION_PATH, "[]", "utf8");
  }
}

export function createCollection() {
  writeFileSync(COLLECTION_PATH, "[]", "utf8");
}

export function upsertRows(rows) {
  const existing = load();
  const byId = new Map(existing.map((r) => [r.id, r]));
  for (const row of rows) {
    byId.set(row.id, row);
  }
  persist([...byId.values()]);
}

export function insertRows(rows) {
  upsertRows(rows);
}

export function entityCount() {
  return load().length;
}
