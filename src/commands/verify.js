import { resolveBackend, logActiveBackend, getStore } from "../store/factory.js";

export async function runVerify() {
  const backend = resolveBackend();
  logActiveBackend(backend);
  const store = await getStore(backend);

  const vectorCount = await store.entityCount();
  const articles = await store.listArticles();
  const articleCount = articles.length;

  if (vectorCount === articleCount) {
    process.stdout.write(`OK: ${articleCount} articles, ${vectorCount} vectors\n`);
    process.exit(0);
  } else {
    const delta = Math.abs(vectorCount - articleCount);
    process.stdout.write(
      `MISMATCH: ${articleCount} articles, ${vectorCount} vectors (delta: ${delta})\n`
    );
    process.exit(1);
  }
}
