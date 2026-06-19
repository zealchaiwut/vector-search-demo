import { resolveBackend, logActiveBackend, getStore } from "../store/factory.js";

export async function runPing() {
  const backend = resolveBackend();
  logActiveBackend(backend);
  const store = await getStore(backend);
  try {
    const { address, version } = await store.ping();
    if (backend === "mock") {
      process.stdout.write(`Mock store: no live connection required (${address})\n`);
    } else {
      process.stdout.write(`${backend} reachable at ${address} (version ${version})\n`);
    }
    process.exit(0);
  } catch (err) {
    process.stderr.write(
      `Failed to connect to ${backend}: ${err.message}\n`
    );
    if (backend === "milvus") {
      process.stderr.write("Is it running? Try npm run milvus:up\n");
    }
    process.exit(1);
  }
}
