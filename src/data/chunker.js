/**
 * Word-window chunker for vector-search-demo.
 * Splits article bodies into overlapping word-window chunks.
 */

const DEFAULT_WORD_SIZE = 120;
const DEFAULT_OVERLAP = 30;

/**
 * Split an article into overlapping word-window chunks.
 * @param {object} article - { id, headline, details }
 * @param {number} wordSize - target words per chunk (default 120)
 * @param {number} overlap - word overlap between consecutive chunks (default 30)
 * @returns {Array<{id, headline, details, attachment_url}>}
 */
export function chunkDocument(article, wordSize = DEFAULT_WORD_SIZE, overlap = DEFAULT_OVERLAP) {
  const { id, headline, details } = article;
  const words = details.trim().split(/\s+/).filter((w) => w.length > 0);

  if (words.length === 0) return [];

  const stride = wordSize - overlap;
  const chunks = [];
  let i = 0;

  while (i < words.length) {
    const slice = words.slice(i, i + wordSize);
    chunks.push({
      id: `${id}:${chunks.length}`,
      headline,
      details: slice.join(" "),
      attachment_url: `/download/${id}`,
    });
    if (i + wordSize >= words.length) break;
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
