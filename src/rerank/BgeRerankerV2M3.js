/**
 * BgeRerankerV2M3 — cross-encoder reranker implementation.
 *
 * Primary path: Transformers.js ONNX pipeline (Xenova/bge-reranker-v2-m3).
 * Fallback path: local sidecar subprocess with character n-gram scoring.
 *
 * The fallback activates automatically when the ONNX model cannot be loaded
 * (package absent, network unavailable, model not in ONNX format). No
 * caller-side changes are required.
 *
 * Model ID override: set RERANKER_MODEL_ID env var (useful for testing).
 */

import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const SIDECAR_PATH = join(__dirname, "sidecar.js");

function scoreViaSidecar(query, chunks) {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, [SIDECAR_PATH], {
      stdio: ["pipe", "pipe", "pipe"],
    });

    let out = "";
    let err = "";
    child.stdout.on("data", (d) => { out += d; });
    child.stderr.on("data", (d) => { err += d; });

    child.on("close", (code) => {
      if (code !== 0) {
        reject(new Error(`Reranker sidecar exited with code ${code}: ${err}`));
        return;
      }
      try {
        const { scores } = JSON.parse(out);
        resolve(scores);
      } catch (e) {
        reject(new Error(`Sidecar output parse error: ${e.message} — raw: ${out}`));
      }
    });

    child.stdin.write(JSON.stringify({ query, chunks }));
    child.stdin.end();
  });
}

export class BgeRerankerV2M3 {
  #tokenizer = null;
  #model = null;
  #useSidecar = false;
  #initialized = false;

  async #init() {
    if (this.#initialized) return;
    this.#initialized = true;

    // Default to bge-reranker-base: multilingual (scores Thai + English), an
    // ungated Xenova ONNX export, unlike bge-reranker-v2-m3 which is gated and
    // fails to download (which is why reranking silently fell back to the weak
    // n-gram sidecar). Override with RERANKER_MODEL_ID.
    const modelId =
      process.env.RERANKER_MODEL_ID ?? "Xenova/bge-reranker-base";

    try {
      const { AutoTokenizer, AutoModelForSequenceClassification } = await import(
        "@xenova/transformers"
      );
      this.#tokenizer = await AutoTokenizer.from_pretrained(modelId);
      this.#model = await AutoModelForSequenceClassification.from_pretrained(modelId);
      // eslint-disable-next-line no-console
      console.log(`[rerank] active model: ${modelId}`);
    } catch (err) {
      this.#useSidecar = true;
      // eslint-disable-next-line no-console
      console.warn(
        `[rerank] model load failed (${err?.message ?? err}); using n-gram sidecar fallback`,
      );
    }
  }

  /**
   * Score each chunk against the query with a cross-encoder.
   *
   * @param {string} query
   * @param {string[]} chunks
   * @returns {Promise<number[]>} Raw relevance logits per chunk (higher = more
   *   relevant). Left un-squashed so downstream ranking keeps full spread.
   */
  async rerank(query, chunks) {
    if (!Array.isArray(chunks) || chunks.length === 0) return [];

    await this.#init();

    if (this.#useSidecar) {
      return scoreViaSidecar(query, chunks);
    }

    // Cross-encoder pair scoring, batched: tokenize (query, chunk) for every
    // chunk in one pass, run a single forward pass, read the relevance logit.
    const inputs = this.#tokenizer(
      new Array(chunks.length).fill(query),
      { text_pair: chunks, padding: true, truncation: true },
    );
    const { logits } = await this.#model(inputs);
    const data = logits.data; // shape [n, 1] flattened row-major
    return chunks.map((_, i) => Number(data[i]));
  }
}
