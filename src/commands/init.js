import { resolveBackend, logActiveBackend, getStore } from "../store/factory.js";

export async function runInit() {
  const backend = resolveBackend();
  logActiveBackend(backend);
  const store = await getStore(backend);
  await store.createCollection();
  const count = await store.entityCount();
  process.stdout.write(
    `Collection 'documents' provisioned: empty (${count} entities), indexed and ready\n`
  );
}
