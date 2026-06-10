import Fastify from "fastify";
import { readFile } from "node:fs/promises";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { config } from "../config.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const PUBLIC_DIR = join(__dirname, "..", "..", "public");

export async function createServer() {
  const app = Fastify({ logger: false });

  app.get("/health", async () => {
    return { status: "ok" };
  });

  app.get("/", async (_req, reply) => {
    const html = await readFile(join(PUBLIC_DIR, "index.html"), "utf-8");
    reply.type("text/html").send(html);
  });

  return app;
}

export async function startServer() {
  const app = await createServer();
  await app.listen({ port: config.port, host: "0.0.0.0" });
  console.log(`Server running at http://localhost:${config.port}`);
}
