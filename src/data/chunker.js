/**
 * Word-window chunker for vector-search-demo.
 * Splits document bodies into overlapping word-window chunks.
 */

const DEFAULT_WORD_SIZE = 120;
const DEFAULT_OVERLAP = 30;

/**
 * Split a document into overlapping word-window chunks.
 * @param {object} doc - { doc_id, title, body }
 * @param {number} wordSize - target words per chunk (default 120)
 * @param {number} overlap - word overlap between consecutive chunks (default 30)
 * @returns {Array<{doc_id, chunk_id, title, text, attachment_name}>}
 */
export function chunkDocument(doc, wordSize = DEFAULT_WORD_SIZE, overlap = DEFAULT_OVERLAP) {
  const { doc_id, title, body } = doc;
  const words = body.trim().split(/\s+/).filter((w) => w.length > 0);

  if (words.length === 0) return [];

  const stride = wordSize - overlap;
  const chunks = [];
  let i = 0;

  while (i < words.length) {
    const slice = words.slice(i, i + wordSize);
    chunks.push({
      doc_id,
      chunk_id: `${doc_id}:${chunks.length}`,
      title,
      text: slice.join(" "),
      attachment_name: `${doc_id}.txt`,
    });
    if (i + wordSize >= words.length) break;
    i += stride;
  }

  return chunks;
}

/**
 * Chunk an array of documents.
 * @param {Array} docs
 * @returns {Array} flat array of all chunks
 */
export function chunkDocuments(docs) {
  return docs.flatMap((doc) => chunkDocument(doc));
}
