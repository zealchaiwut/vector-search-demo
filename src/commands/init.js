import { createCollection } from "../data/collection.js";

export async function runInit() {
  await createCollection();
  process.stdout.write(
    `Collection 'documents' provisioned: indexed and ready\n`
  );
}
