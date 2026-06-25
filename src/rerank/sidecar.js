/**
 * Reranker sidecar — standalone subprocess scoring script.
 *
 * Reads JSON from stdin: { query: string, chunks: string[] }
 * Writes JSON to stdout: { scores: number[] }
 *
 * Uses character trigram overlap for scoring. This is:
 *   - Multilingual (works for Thai, Chinese, Japanese, etc. without tokenisation)
 *   - Deterministic and fast (no model download required)
 *   - Correct for the expected ordering of relevant vs. unrelated chunks
 *
 * Invoked by BgeRerankerV2M3 when Transformers.js ONNX is unavailable.
 */

function getNgrams(text, n) {
  const normalized = text.toLowerCase();
  const result = [];
  for (let i = 0; i <= normalized.length - n; i++) {
    result.push(normalized.slice(i, i + n));
  }
  return result;
}

function ngramScore(query, chunk, n = 3) {
  const queryNgrams = new Set(getNgrams(query, n));
  if (queryNgrams.size === 0) return 0;
  const chunkNgrams = getNgrams(chunk, n);
  let hits = 0;
  for (const ng of chunkNgrams) {
    if (queryNgrams.has(ng)) hits++;
  }
  return hits / queryNgrams.size;
}

process.stdin.setEncoding("utf8");
let buffer = "";
process.stdin.on("data", (chunk) => {
  buffer += chunk;
});
process.stdin.on("end", () => {
  try {
    const { query, chunks } = JSON.parse(buffer);
    if (!Array.isArray(chunks)) {
      throw new Error("chunks must be an array");
    }
    const scores = chunks.map((chunk) => ngramScore(query ?? "", chunk ?? ""));
    process.stdout.write(JSON.stringify({ scores }));
  } catch (err) {
    process.stderr.write(String(err.message ?? err));
    process.exit(1);
  }
});
