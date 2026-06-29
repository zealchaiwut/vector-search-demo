/**
 * Reciprocal Rank Fusion (RRF) utilities for hybrid dense + lexical retrieval.
 *
 * Formula: score = 1/(k + dense_rank) + 1/(k + lexical_rank)
 * where null rank means the result was absent from that list (term omitted).
 */

/**
 * Compute the RRF fused score for a single result.
 *
 * @param {number|null} denseRank   1-indexed rank in the dense result list, or null.
 * @param {number|null} lexicalRank 1-indexed rank in the lexical result list, or null.
 * @param {number} k                RRF constant (default 60).
 * @returns {number}
 */
export function computeRrfScore(denseRank, lexicalRank, k = 60) {
  let score = 0;
  if (denseRank !== null && denseRank !== undefined) score += 1 / (k + denseRank);
  if (lexicalRank !== null && lexicalRank !== undefined) score += 1 / (k + lexicalRank);
  return score;
}

/**
 * Merge two ranked result lists using RRF.
 *
 * Each list item must have an `id` and `chunk_index` field so duplicates are
 * matched across lists. The returned array is sorted by descending RRF score
 * and each entry gets `dense_rank`, `lexical_rank`, and `fused_score` fields.
 *
 * @param {Array<object>} denseResults   Flat chunk rows from the dense path.
 * @param {Array<object>} lexicalResults Flat chunk rows from the lexical path.
 * @param {number} k                     RRF constant.
 * @returns {Array<object>}
 */
export function mergeRrf(denseResults, lexicalResults, k = 60) {
  const key = (r) => `${r.article_id ?? r.id}:${r.chunk_index ?? 0}`;

  // Index ranks (1-based) for each list.
  const denseRankMap = new Map(denseResults.map((r, i) => [key(r), i + 1]));
  const lexicalRankMap = new Map(lexicalResults.map((r, i) => [key(r), i + 1]));

  // Union of all unique chunk keys.
  const allKeys = new Set([...denseRankMap.keys(), ...lexicalRankMap.keys()]);

  // Build a lookup for the row data (dense has preference; lexical fills gaps).
  const rowByKey = new Map();
  for (const r of lexicalResults) rowByKey.set(key(r), r);
  for (const r of denseResults) rowByKey.set(key(r), r);

  const fused = [];
  for (const k_ of allKeys) {
    const denseRank = denseRankMap.get(k_) ?? null;
    const lexicalRank = lexicalRankMap.get(k_) ?? null;
    const fusedScore = computeRrfScore(denseRank, lexicalRank, k);
    const row = rowByKey.get(k_);
    fused.push({
      ...row,
      score: parseFloat(fusedScore.toFixed(6)),
      dense_rank: denseRank,
      lexical_rank: lexicalRank,
      fused_score: parseFloat(fusedScore.toFixed(6)),
    });
  }

  return fused.sort((a, b) => b.fused_score - a.fused_score);
}
