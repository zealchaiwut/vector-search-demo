import { getMilvusClient } from "../milvus/client.js";

export async function runPing() {
  const client = getMilvusClient();
  try {
    const version = await client.ping();
    const address = client.getAddress();
    process.stdout.write(`Milvus reachable at ${address} (version ${version})\n`);
    process.exit(0);
  } catch (err) {
    process.stderr.write(
      `Failed to connect to Milvus: ${err.message}\nIs it running? Try npm run milvus:up\n`
    );
    process.exit(1);
  }
}
