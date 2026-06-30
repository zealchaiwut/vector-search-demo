/**
 * Lexical scorer interface — encapsulates the active scorer implementation
 * behind a stable call site (searchLexical) so that a future segmentation-based
 * scorer can be swapped in without touching any other module.
 *
 * Default implementation: tsvectorOrScorer — OR tsquery with ts_rank_cd.
 *   - English: to_tsquery('english', 'term1 | term2') against the ts column
 *   - Thai: Intl.Segmenter word-tokens → to_tsquery('simple', ...) against ts_simple
 *   Falls back to trigramScorer when ts_simple column is unavailable.
 * Swap via: setLexicalScorer(myFn)
 */

import { tsvectorOrScorer } from "./tsvectorOrScorer.js";

let _scorer = tsvectorOrScorer;

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
