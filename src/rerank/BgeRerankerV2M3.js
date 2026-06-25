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
  #pipe = null;
  #useSidecar = false;
  #initialized = false;

  async #init() {
    if (this.#initialized) return;
    this.#initialized = true;

    const modelId =
      process.env.RERANKER_MODEL_ID ?? "Xenova/bge-reranker-v2-m3";

    try {
      const { pipeline } = await import("@xenova/transformers");
      this.#pipe = await pipeline("text-classification", modelId);
    } catch {
      this.#useSidecar = true;
    }
  }

  /**
   * Score each chunk against the query.
   *
   * @param {string} query
   * @param {string[]} chunks
   * @returns {Promise<number[]>} Relevance score per chunk (higher = more relevant).
   */
  async rerank(query, chunks) {
    if (!Array.isArray(chunks) || chunks.length === 0) return [];

    await this.#init();

    if (this.#useSidecar) {
      return scoreViaSidecar(query, chunks);
    }

    // Cross-encoder: score each (query, chunk) pair.
    const results = await Promise.all(
      chunks.map((chunk) => this.#pipe([[query, chunk]]))
    );

    return results.map((r) => {
      const item = Array.isArray(r) ? r[0] : r;
      return typeof item?.score === "number" ? item.score : 0;
    });
  }
}
