/**
 * Lexical scorer interface — encapsulates the active scorer implementation
 * behind a stable call site (searchLexical) so that a future segmentation-based
 * scorer can be swapped in without touching any other module.
 *
 * Default implementation: trigramScorer (pg_trgm word_similarity).
 * Swap via: setLexicalScorer(mySegmenterFn)
 */

import { trigramScorer } from "./trigramScorer.js";

let _scorer = trigramScorer;

/**
 * Replace the active lexical scorer without changing call sites.
 *
 * @param {(store: object, query: string, k: number) => Promise<Array>} fn
 */
export function setLexicalScorer(fn) {
  _scorer = fn;
}

/**
 * Run lexical scoring via the active scorer implementation.
 *
 * @param {import("../../store/PgVectorStore.js").PgVectorStore} store
 * @param {string} query
 * @param {number} k
 * @returns {Promise<Array<{id: string, chunk_index: number, headline: string, details: string, attachment_url: string|null, lexical_score: number}>>}
 */
export async function searchLexical(store, query, k) {
  return _scorer(store, query, k);
}
