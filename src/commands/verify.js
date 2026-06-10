import { entityCount, listArticles } from "../data/collection.js";

export async function runVerify() {
  const vectorCount = entityCount();
  const articleCount = listArticles().length;

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
