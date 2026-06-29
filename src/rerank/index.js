/**
 * Reranker factory — the sole public resolution point for the Reranker interface.
 *
 * Consumers import createReranker() and call rerank(query, chunks).
 * To swap implementations, change only this file.
 *
 * Reranker interface (duck-typed):
 *   rerank(query: string, chunks: string[]): Promise<number[]>
 *   Returns one relevance score per chunk; higher score = more relevant.
 */

import { BgeRerankerV2M3 } from "./BgeRerankerV2M3.js";

let _reranker = null;

/**
 * Return the default Reranker implementation (BgeRerankerV2M3).
 * The instance is cached after the first call.
 *
 * @returns {BgeRerankerV2M3}
 */
export function createReranker() {
  if (!_reranker) {
    _reranker = new BgeRerankerV2M3();
  }
  return _reranker;
}

export { BgeRerankerV2M3 };
