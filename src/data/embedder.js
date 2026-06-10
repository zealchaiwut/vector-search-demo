/**
 * Batch TF-IDF embedder for vector-search-demo.
 * Builds IDF over the full chunk corpus then embeds all chunks at once.
 */

function tokenize(text) {
  return text.toLowerCase().match(/\b[a-z0-9]+\b/g) ?? [];
}

function buildIDF(chunks) {
  const N = chunks.length;
  const df = new Map();
  for (const chunk of chunks) {
    for (const token of new Set(tokenize(chunk.text))) {
      df.set(token, (df.get(token) ?? 0) + 1);
    }
  }
  const idf = new Map();
  for (const [token, count] of df) {
    idf.set(token, Math.log((N + 1) / (count + 1)) + 1);
  }
  return idf;
}

function embedText(text, vocab, idf) {
  const tokens = tokenize(text);
  if (tokens.length === 0) return new Float64Array(vocab.size);

  const tf = new Map();
  for (const t of tokens) tf.set(t, (tf.get(t) ?? 0) + 1);

  const vec = new Float64Array(vocab.size);
  for (const [token, count] of tf) {
    const idx = vocab.get(token);
    if (idx !== undefined) {
      vec[idx] = (count / tokens.length) * (idf.get(token) ?? Math.log(2));
    }
  }

  // L2 normalize
  let norm = 0;
  for (const v of vec) norm += v * v;
  norm = Math.sqrt(norm);
  if (norm === 0) return vec;
  for (let i = 0; i < vec.length; i++) vec[i] /= norm;

  return vec;
}

/**
 * Batch-embed an array of chunks using TF-IDF over the full corpus.
 * IDF is computed once over all chunks before any individual embedding is produced.
 * @param {Array<object>} chunks - each has at least a `text` field
 * @returns {Array<object>} same chunks with `embedding` field added (Array of floats)
 */
export function batchEmbed(chunks) {
  if (chunks.length === 0) return [];

  // Build IDF from the full corpus in one pass
  const idf = buildIDF(chunks);

  // Build a deterministic vocabulary index
  const vocab = new Map();
  for (const [token] of idf) {
    vocab.set(token, vocab.size);
  }

  return chunks.map((chunk) => {
    const vec = embedText(chunk.text, vocab, idf);
    return { ...chunk, embedding: Array.from(vec) };
  });
}
