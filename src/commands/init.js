import { createCollection, entityCount } from "../data/collection.js";

export async function runInit() {
  await createCollection();
  const count = await entityCount();
  process.stdout.write(
    `Collection 'documents' provisioned: empty (${count} entities), indexed and ready\n`
  );
}
