/**
 * Reranker — scores (query, passage) pairs and returns reranked results.
 *
 * Uses term-frequency scoring as a cross-encoder approximation: results whose
 * text contains more query terms more densely are scored higher. A production
 * deployment would replace this body with a loaded cross-encoder model call.
 */
export class Reranker {
  /**
   * Rerank candidates for a given query.
   *
   * @param {string} query
   * @param {Array<object>} candidates - flat result objects (headline, details, score, …)
   * @returns {Array<{ result: object, rerankScore: number, preRerankRank: number, postRerankRank: number }>}
   *   Items sorted by descending rerankScore; each carries pre/post rank and rerank score.
   */
  rerank(query, candidates) {
    const terms = (query ?? "").toLowerCase().split(/\s+/).filter(Boolean);

    const scored = candidates.map((result, idx) => {
      const text = `${result.headline ?? ""} ${result.details ?? ""}`.toLowerCase();
      let rerankScore = 0;
      if (terms.length > 0) {
        const textLen = Math.max(text.length, 1);
        for (const term of terms) {
          let count = 0;
          let pos = 0;
          while ((pos = text.indexOf(term, pos)) !== -1) {
            count++;
            pos += term.length;
          }
          if (count > 0) {
            rerankScore += Math.log(1 + count) / Math.log(1 + textLen / Math.max(term.length, 1));
          }
        }
      }
      return {
        result,
        rerankScore: parseFloat(rerankScore.toFixed(4)),
        preRerankRank: idx + 1,
      };
    });

    return scored
      .sort((a, b) => b.rerankScore - a.rerankScore)
      .map((item, idx) => ({ ...item, postRerankRank: idx + 1 }));
  }
}
