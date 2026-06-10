import { createCollection, entityCount } from "../data/collection.js";

export async function runInit() {
  // Provision an empty, indexed file-backed collection (idempotent reset).
  createCollection();
  process.stdout.write(
    `Collection 'documents' provisioned: empty (${entityCount()} entities), indexed and ready\n`
  );
}
