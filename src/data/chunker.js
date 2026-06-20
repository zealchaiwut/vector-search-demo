/**
 * Character-window chunker for vector-search-demo.
 * Splits article bodies into overlapping fixed-length character chunks.
 * Character-based (not whitespace-based) so it works correctly for Thai and
 * other scripts that have no space between words.
 *
 * Override defaults via environment variables:
 *   CHUNK_SIZE    — characters per chunk (default: 400)
 *   CHUNK_OVERLAP — overlap between consecutive chunks (default: 80)
 */

export const CHUNK_SIZE = 400;
export const CHUNK_OVERLAP = 80;

/**
 * Split an article into overlapping character-window chunks.
 * CHUNK_SIZE and CHUNK_OVERLAP env vars override the defaults at call time.
 * @param {object} article - { id, headline, details, attachment_url }
 * @param {number} chunkSize - characters per chunk (default CHUNK_SIZE)
 * @param {number} overlap - character overlap between consecutive chunks (default CHUNK_OVERLAP)
 * @returns {Array<{id, headline, details, attachment_url}>}
 */
export function chunkDocument(article, chunkSize = CHUNK_SIZE, overlap = CHUNK_OVERLAP) {
  const sz = parseInt(process.env.CHUNK_SIZE ?? "", 10) || chunkSize;
  const ov = parseInt(process.env.CHUNK_OVERLAP ?? "", 10) || overlap;
  const { id, headline, details } = article;
  const text = (details ?? "").trim();

  if (text.length === 0) return [];

  const stride = sz - ov;
  const chunks = [];
  let i = 0;

  while (i < text.length) {
    const slice = text.slice(i, i + sz);
    chunks.push({
      id: `${id}:${chunks.length}`,
      headline,
      details: slice,
      attachment_url: article.attachment_url || `/download/${id}`,
    });
    if (i + sz >= text.length) break;
    i += stride;
  }

  return chunks;
}

/**
 * Chunk an array of articles.
 * @param {Array} articles
 * @returns {Array} flat array of all chunks
 */
export function chunkDocuments(articles) {
  return articles.flatMap((article) => chunkDocument(article));
}
