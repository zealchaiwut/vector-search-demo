import { createCollection } from "../milvus/schema.js";

export async function runInit(args = []) {
  const recreate = args.includes("--recreate");
  await createCollection(recreate);
  process.stdout.write(`Collection 'documents' provisioned\n`);
}
