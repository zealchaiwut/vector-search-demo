import { createEmbedder } from "../embeddings/index.js";

let _embedder = null;

async function getEmbedder() {
  if (!_embedder) {
    _embedder = await createEmbedder();
  }
  return _embedder;
}

/**
 * Batch-embed an array of chunks using the configured EMBEDDING_MODEL.
 * Each chunk's details is prefixed with "passage: " as required by e5 instruction format.
 * For BGE-M3, also generates and attaches sparse_embedding alongside the dense embedding.
 * @param {Array<object>} chunks - each has at least a `details` field
 * @returns {Promise<Array<object>>} same chunks with `embedding` (and optionally
 *   `sparse_embedding`) added
 */
export async function batchEmbed(chunks) {
  if (chunks.length === 0) return [];

  const embedder = await getEmbedder();
  const texts = chunks.map((c) => `passage: ${c.details}`);
  const vectors = await embedder.embed(texts);

  if (vectors.length > 0 && vectors[0].length !== embedder.dim) {
    throw new Error(
      `Embedding dimension mismatch: config DIM=${embedder.dim}, model output=${vectors[0].length}`
    );
  }

  const result = chunks.map((chunk, i) => ({
    ...chunk,
    embedding: vectors[i],
  }));

  // For BGE-M3, attach sparse vectors for the lexical hybrid-search component.
  if (embedder.sparse) {
    const sparseVecs = await embedder.embedSparse(texts);
    for (let i = 0; i < result.length; i++) {
      result[i].sparse_embedding = sparseVecs[i] ?? {};
    }
  }

  return result;
}
