/**
 * Character-window chunker for vector-search-demo.
 * Splits article bodies into overlapping fixed-length character chunks.
 * Character-based (not whitespace-based) so it works correctly for Thai and
 * other scripts that have no space between words.
 */

export const CHUNK_SIZE = 500;
export const CHUNK_OVERLAP = 100;

/**
 * Split an article into overlapping character-window chunks.
 * @param {object} article - { id, headline, details, attachment_url }
 * @param {number} chunkSize - characters per chunk (default CHUNK_SIZE)
 * @param {number} overlap - character overlap between consecutive chunks (default CHUNK_OVERLAP)
 * @returns {Array<{id, headline, details, attachment_url}>}
 */
export function chunkDocument(article, chunkSize = CHUNK_SIZE, overlap = CHUNK_OVERLAP) {
  const { id, headline, details } = article;
  const text = (details ?? "").trim();

  if (text.length === 0) return [];

  const stride = chunkSize - overlap;
  const chunks = [];
  let i = 0;

  while (i < text.length) {
    const slice = text.slice(i, i + chunkSize);
    chunks.push({
      id: `${id}:${chunks.length}`,
      headline,
      details: slice,
      attachment_url: article.attachment_url || `/download/${id}`,
    });
    if (i + chunkSize >= text.length) break;
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
