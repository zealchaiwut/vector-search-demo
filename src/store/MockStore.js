/**
 * MockStore: in-memory VectorStore implementation.
 *
 * Activated via DB_BACKEND=mock. Seeds itself from the bundled sample article
 * set on first use. All mutations (upsert, delete) are visible immediately
 * within the same process but are not persisted across restarts.
 *
 * Search uses brute-force cosine similarity over stored chunk embeddings —
 * identical ranking logic to the file-backed backend, but with no I/O.
 */

import { generateDocuments } from "../data/generator.js";
import { chunkDocuments } from "../data/chunker.js";
import { batchEmbed } from "../data/embedder.js";
import { createEmbedder } from "../embeddings/index.js";

// Over-fetch factor for chunk candidates before collapsing to articles
const EF = 64;

// ---------------------------------------------------------------------------
// Vector math
// ---------------------------------------------------------------------------

function dotProduct(a, b) {
  let sum = 0;
  for (let i = 0; i < a.length; i++) sum += a[i] * b[i];
  return sum;
}

// MiniLM embeddings are L2-normalised so cosine similarity equals dot product.
function cosineSimilarity(a, b) {
  return dotProduct(a, b);
}

// ---------------------------------------------------------------------------
// Sentence splitting for best_passage extraction
// ---------------------------------------------------------------------------

function splitIntoSentences(text) {
  const sentences = [];
  let segStart = 0;
  const len = text.length;

  for (let i = 0; i < len; i++) {
    const ch = text[i];
    if (ch === "." || ch === "!" || ch === "?") {
      let j = i + 1;
      while (j < len && text[j] === " ") j++;
      if (j >= len || (text[j] >= "A" && text[j] <= "Z")) {
        const raw = text.slice(segStart, i + 1);
        const trimmed = raw.trim();
        if (trimmed.length > 0) {
          const lead = raw.length - raw.trimStart().length;
          const start = segStart + lead;
          sentences.push({ text: trimmed, start, end: start + trimmed.length });
        }
        segStart = j;
        i = j - 1;
      }
    }
  }

  if (segStart < len) {
    const raw = text.slice(segStart);
    const trimmed = raw.trim();
    if (trimmed.length > 0) {
      const lead = raw.length - raw.trimStart().length;
      const start = segStart + lead;
      sentences.push({ text: trimmed, start, end: start + trimmed.length });
    }
  }

  return sentences;
}

const CONTEXT_SENTENCES = 2;

async function selectBestPassage(docText, queryEmbedding, embedder) {
  const sentences = splitIntoSentences(docText);
  if (sentences.length === 0) {
    const trimmed = docText.trim();
    return { text: trimmed, start_offset: 0, end_offset: trimmed.length, context: { before: "", after: "" } };
  }

  const vectors = await embedder.embed(sentences.map((s) => s.text));

  let bestIdx = 0;
  let bestScore = -Infinity;
  for (let i = 0; i < sentences.length; i++) {
    const score = cosineSimilarity(queryEmbedding, vectors[i]);
    if (score > bestScore) {
      bestScore = score;
      bestIdx = i;
    }
  }

  const best = sentences[bestIdx];
  const before = sentences
    .slice(Math.max(0, bestIdx - CONTEXT_SENTENCES), bestIdx)
    .map((s) => s.text)
    .join(" ");
  const after = sentences
    .slice(bestIdx + 1, bestIdx + 1 + CONTEXT_SENTENCES)
    .map((s) => s.text)
    .join(" ");

  return {
    text: best.text,
    start_offset: best.start,
    end_offset: best.end,
    context: { before, after },
  };
}

// ---------------------------------------------------------------------------
// Attachment URL type discriminator
// ---------------------------------------------------------------------------

function resolveAttachmentUrlType(url) {
  if (!url) return null;
  if (url.startsWith("/download/")) return "local";
  return "external";
}

// ---------------------------------------------------------------------------
// MockStore
// ---------------------------------------------------------------------------

export class MockStore {
  constructor() {
    /** @type {Array<{id: string, headline: string, details: string, attachment_url: string, embedding: number[]}>} */
    this._chunks = [];
    this._seeded = false;
    this._seedPromise = null;
    this._embedder = null;
  }

  // Lazy init: called before any operation that needs data.
  async _ensureSeeded() {
    if (this._seeded) return;
    if (!this._seedPromise) this._seedPromise = this._doSeed();
    await this._seedPromise;
  }

  async _doSeed() {
    const articles = generateDocuments();
    const chunks = chunkDocuments(articles);
    const embedded = await batchEmbed(chunks);
    this._chunks = embedded.map((c) => ({
      id: c.id,
      headline: c.headline,
      details: c.details,
      attachment_url: c.attachment_url ?? `/download/${c.id.split(":")[0]}`,
      embedding: c.embedding,
    }));
    this._seeded = true;
  }

  async _getEmbedder() {
    if (!this._embedder) this._embedder = await createEmbedder();
    return this._embedder;
  }

  // -------------------------------------------------------------------------
  // VectorStore interface
  // -------------------------------------------------------------------------

  /** Health check — always resolves successfully. */
  async ping() {
    return { ok: true };
  }

  /** Number of distinct articles currently in memory. */
  async count() {
    await this._ensureSeeded();
    const ids = new Set(this._chunks.map((c) => c.id.split(":")[0]));
    return ids.size;
  }

  /**
   * Add or replace an article (matched by id).
   * Chunks and embeds the article body before storing.
   */
  async upsert(article) {
    await this._ensureSeeded();
    // Remove all existing chunks for this article id
    this._chunks = this._chunks.filter((c) => c.id.split(":")[0] !== article.id);
    // Chunk the new article body and embed
    const chunks = chunkDocuments([article]);
    const embedded = await batchEmbed(chunks);
    for (const c of embedded) {
      this._chunks.push({
        id: c.id,
        headline: c.headline,
        details: c.details,
        attachment_url: c.attachment_url ?? `/download/${article.id}`,
        embedding: c.embedding,
      });
    }
  }

  /**
   * Remove the article with the given id from memory.
   * Returns true if something was removed, false if the id was not found.
   */
  async delete(articleId) {
    await this._ensureSeeded();
    const before = this._chunks.length;
    this._chunks = this._chunks.filter((c) => c.id.split(":")[0] !== articleId);
    return this._chunks.length < before;
  }

  /**
   * Brute-force cosine similarity search.
   * Returns up to k articles ranked by descending score, each with best_passage.
   */
  async search(query, k = 10) {
    await this._ensureSeeded();

    const trimmed = (query ?? "").trim();
    if (!trimmed || this._chunks.length === 0) return [];

    const embedder = await this._getEmbedder();
    const [queryEmbedding] = await embedder.embed([trimmed]);

    // Score every chunk
    const scored = this._chunks
      .filter((c) => Array.isArray(c.embedding) && c.embedding.length > 0)
      .map((c) => ({
        articleId: c.id.split(":")[0],
        id: c.id,
        headline: c.headline,
        details: c.details,
        attachment_url: c.attachment_url,
        score: cosineSimilarity(queryEmbedding, c.embedding),
      }));

    // Over-fetch then collapse: keep best-scoring chunk per article
    const candidates = scored.sort((a, b) => b.score - a.score).slice(0, EF);
    const byArticleId = new Map();
    for (const c of candidates) {
      if (!byArticleId.has(c.articleId) || c.score > byArticleId.get(c.articleId).score) {
        byArticleId.set(c.articleId, c);
      }
    }

    // Stitch full article text across chunks for best_passage selection
    const articleTexts = new Map();
    for (const chunk of this._chunks) {
      const aid = chunk.id.split(":")[0];
      articleTexts.set(aid, (articleTexts.get(aid) ?? "") + (articleTexts.has(aid) ? " " : "") + chunk.details);
    }

    const top = [...byArticleId.values()]
      .filter((r) => r.score > 0)
      .sort((a, b) => b.score - a.score)
      .slice(0, k);

    return Promise.all(
      top.map(async (r) => {
        const articleText = articleTexts.get(r.articleId) ?? r.details;
        const best_passage = await selectBestPassage(articleText, queryEmbedding, embedder);
        return {
          id: r.articleId,
          headline: r.headline,
          details: r.details.replace(/\s+/g, " ").trim().slice(0, 240),
          score: parseFloat(r.score.toFixed(4)),
          attachment_url: r.attachment_url ?? null,
          attachment_url_type: resolveAttachmentUrlType(r.attachment_url),
          best_passage,
        };
      })
    );
  }
}
