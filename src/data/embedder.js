import { createEmbedder } from "../embeddings/index.js";

let _embedder = null;

async function getEmbedder() {
  if (!_embedder) {
    _embedder = await createEmbedder();
  }
  return _embedder;
}

/**
 * Batch-embed an array of chunks using multilingual-e5-small via createEmbedder.
 * Each chunk's details is prefixed with "passage: " as required by the e5 instruction format.
 * @param {Array<object>} chunks - each has at least a `details` field
 * @returns {Promise<Array<object>>} same chunks with `embedding` field added (384 floats each)
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

  return chunks.map((chunk, i) => ({
    ...chunk,
    embedding: vectors[i],
  }));
}
