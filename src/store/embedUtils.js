/**
 * Shared embedding utilities.
 *
 * avgEmbeddings and collapseToArticles were previously duplicated byte-for-byte
 * in src/data/collection.js and src/store/postgres.js (issue #59). They live
 * here as the single canonical source.
 *
 * Note: with the chunk-granularity storage model introduced in issue #80,
 * embeddings are stored per-chunk without averaging. These functions remain
 * available for any context that needs to reconstitute article-level
 * representations from chunk rows (e.g. export, evaluation, or legacy callers).
 */

/**
 * Average a set of equal-length float embedding vectors element-wise.
 * Returns [] when given an empty input.
 *
 * @param {number[][]} embeddings
 * @returns {number[]}
 */
export function avgEmbeddings(embeddings) {
  if (embeddings.length === 0) return [];
  const dim = embeddings[0].length;
  const avg = new Array(dim).fill(0);
  for (const v of embeddings) {
    for (let i = 0; i < dim; i++) avg[i] += v[i];
  }
  for (let i = 0; i < dim; i++) avg[i] /= embeddings.length;
  return avg;
}

/**
 * Collapse chunk rows (id like "articleId:N") into one row per article.
 * Details from each chunk are joined with a space; embeddings are averaged.
 *
 * @param {Array<{id: string, headline: string, details: string, attachment_url: string, embedding?: number[]}>} rows
 * @returns {Array<{id: string, headline: string, details: string, attachment_url: string, embedding: number[]}>}
 */
export function collapseToArticles(rows) {
  const byArticle = new Map();
  for (const row of rows) {
    const articleId = row.id.split(":")[0];
    if (!byArticle.has(articleId)) {
      byArticle.set(articleId, {
        id: articleId,
        headline: row.headline,
        attachment_url: row.attachment_url,
        detailParts: [],
        embeddings: [],
      });
    }
    const entry = byArticle.get(articleId);
    entry.detailParts.push(row.details);
    if (Array.isArray(row.embedding)) entry.embeddings.push(row.embedding);
  }
  return [...byArticle.values()].map((entry) => ({
    id: entry.id,
    headline: entry.headline,
    details: entry.detailParts.join(" "),
    attachment_url: entry.attachment_url,
    embedding: avgEmbeddings(entry.embeddings),
  }));
}
