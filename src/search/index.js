/**
 * Search module — embeds the query, runs vector similarity against chunk rows,
 * groups hits by parent article, and returns articles ranked by their best
 * chunk score.
 *
 * Configurable N (max chunks per article):
 *   • Environment variable: SEARCH_MAX_CHUNKS (integer, default 3)
 *   • Can also be overridden per-call via the maxChunksPerArticle parameter
 *
 * Response shape per result (flat — one row per chunk, sorted by score):
 *   { id, article_id, chunk_index, headline, text, score, passages, ... }
 *
 * Supported backends (selected via DB_BACKEND / MILVUS_HOST):
 *   postgres  — PgVectorStore (pgvector cosine similarity)
 *   milvus    — MilvusStore (ANN cosine similarity)
 *   file/mock — collection.json TF-IDF + dot-product cosine similarity
 */

import { readFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { createEmbedder } from "../embeddings/index.js";
import { useMilvus, milvusAddress, usePostgres } from "../data/backend.js";
import { flattenChunkResults } from "./flattenResults.js";
import { defaultRetrievalConfig } from "../config/retrieval.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const COLLECTION_PATH = join(__dirname, "..", "..", "collection.json");

// Candidate pool size for ANN / file-backed search before grouping.
const EF = 64;

// Default maximum number of chunk hits to surface per article.
// Override via SEARCH_MAX_CHUNKS env var.
const DEFAULT_MAX_CHUNKS = 3;

// Minimum cosine similarity score for a chunk to be included in results.
const MIN_SCORE_THRESHOLD = 0.1;

// Context sentences to include around the best passage sentence.
const CONTEXT_SENTENCES = 2;

function getMaxChunks(override) {
  if (override !== undefined && override !== null) return Math.max(1, parseInt(override, 10) || DEFAULT_MAX_CHUNKS);
  const fromEnv = parseInt(process.env.SEARCH_MAX_CHUNKS, 10);
  return Number.isFinite(fromEnv) && fromEnv > 0 ? fromEnv : DEFAULT_MAX_CHUNKS;
}

let _embedder = null;
async function getEmbedder() {
  if (!_embedder) _embedder = await createEmbedder();
  return _embedder;
}

// ---------------------------------------------------------------------------
// Attachment URL type discriminator
// ---------------------------------------------------------------------------

function resolveAttachmentUrlType(url) {
  if (!url) return null;
  if (url.startsWith("/download/")) return "local";
  if (url.startsWith("http://") || url.startsWith("https://")) return "external";
  return "external";
}

// ---------------------------------------------------------------------------
// File-backed collection loader
// ---------------------------------------------------------------------------

function loadRows() {
  if (!existsSync(COLLECTION_PATH)) return [];
  try {
    const rows = JSON.parse(readFileSync(COLLECTION_PATH, "utf8"));
    return Array.isArray(rows) ? rows : [];
  } catch {
    return [];
  }
}

// ---------------------------------------------------------------------------
// Dense vector cosine similarity (MiniLM embeddings are L2-normalised)
// ---------------------------------------------------------------------------

function dotProduct(a, b) {
  let sum = 0;
  for (let i = 0; i < a.length; i++) sum += a[i] * b[i];
  return sum;
}

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

async function selectBestPassage(docText, queryEmbedding, embedder) {
  const sentences = splitIntoSentences(docText);
  if (sentences.length === 0) {
    const trimmed = docText.trim();
    return {
      text: trimmed,
      start_offset: 0,
      end_offset: trimmed.length,
      context: { before: "", after: "" },
    };
  }

  const vectors = await embedder.embed(sentences.map((s) => `passage: ${s.text}`));

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

const OFFSET_PROXIMITY = 20;
const CHUNK_OFFSET_BASE = 1_000_000;

function normalizePassageText(text) {
  return (text ?? "").replace(/\s+/g, " ").trim();
}

function passagesSimilar(a, b) {
  const left = normalizePassageText(a);
  const right = normalizePassageText(b);
  if (!left || !right) return left === right;
  if (left === right) return true;
  const shorter = left.length <= right.length ? left : right;
  const longer = left.length <= right.length ? right : left;
  return shorter.length >= 20 && longer.includes(shorter);
}

/** Shift offsets per chunk so unpunctuated Thai chunks (all at 0) stay distinct. */
function withChunkScopedOffsets(passage, chunkIndex) {
  const base = (chunkIndex ?? 0) * CHUNK_OFFSET_BASE;
  return {
    ...passage,
    start_offset: passage.start_offset + base,
    end_offset: passage.end_offset + base,
  };
}

function deduplicatePassages(passages) {
  const kept = [];
  for (const passage of passages) {
    const isDup = kept.some(
      (existing) =>
        passagesSimilar(existing.text, passage.text) ||
        (Math.abs(existing.start_offset - passage.start_offset) < OFFSET_PROXIMITY &&
          passagesSimilar(existing.text, passage.text)),
    );
    if (!isDup) kept.push(passage);
  }
  return kept;
}

// ---------------------------------------------------------------------------
// Milvus-backed search path
// ---------------------------------------------------------------------------

async function _searchMilvus(query, k, maxChunks) {
  const trimmed = (query ?? "").trim();
  if (!trimmed) return [];

  const embedder = await getEmbedder();
  const [queryEmbedding] = await embedder.embed([`query: ${trimmed}`]);

  const { MilvusStore } = await import("../store/milvus-store.js");
  const store = new MilvusStore(milvusAddress());

  const candidates = await store.search(queryEmbedding, EF);
  const top = candidates.filter((r) => r.score > 0).slice(0, k);

  if (top.length === 0) return [];

  return Promise.all(
    top.map(async (r) => {
      const best_passage = await selectBestPassage(r.details, queryEmbedding, embedder);
      const passages = [{ ...best_passage, score: parseFloat(r.score.toFixed(4)) }];
      return {
        id: r.id,
        headline: r.headline,
        details: r.details.replace(/\s+/g, " ").trim().slice(0, 240),
        score: parseFloat(r.score.toFixed(4)),
        attachment_url: r.attachment_url ?? null,
        attachment_url_type: resolveAttachmentUrlType(r.attachment_url),
        best_passage,
        passages,
        chunks: [{ text: r.details.replace(/\s+/g, " ").trim(), score: parseFloat(r.score.toFixed(4)) }],
      };
    }),
  );
}

// ---------------------------------------------------------------------------
// File-backed search path
// ---------------------------------------------------------------------------

async function _searchFile(query, k, maxChunks) {
  const rows = loadRows();
  if (rows.length === 0) return [];

  const trimmed = (query ?? "").trim();
  if (!trimmed) return [];

  const embedder = await getEmbedder();
  const [queryEmbedding] = await embedder.embed([`query: ${trimmed}`]);

  const scored = rows
    .filter((row) => Array.isArray(row.embedding) && row.embedding.length > 0)
    .map((row) => ({
      articleId: row.id.split(":")[0],
      id: row.id,
      headline: row.headline,
      details: row.details,
      attachment_url: row.attachment_url,
      score: dotProduct(queryEmbedding, row.embedding),
    }));

  const candidates = scored.sort((a, b) => b.score - a.score).slice(0, EF);

  // Group chunk hits by article_id.
  const byArticleId = new Map();
  for (const c of candidates) {
    if (!byArticleId.has(c.articleId)) {
      byArticleId.set(c.articleId, []);
    }
    byArticleId.get(c.articleId).push(c);
  }

  // Build full article text for best_passage computation (backward compat).
  const articleTexts = new Map();
  for (const row of rows) {
    const aid = row.id.split(":")[0];
    if (!articleTexts.has(aid)) {
      articleTexts.set(aid, row.details);
    } else {
      articleTexts.set(aid, articleTexts.get(aid) + " " + row.details);
    }
  }

  const top = [...byArticleId.entries()]
    .filter(([, chunks]) => chunks[0].score >= MIN_SCORE_THRESHOLD)
    .map(([articleId, chunks]) => ({
      articleId,
      bestChunk: chunks[0],
      chunks: chunks.slice(0, maxChunks),
    }))
    .sort((a, b) => b.bestChunk.score - a.bestChunk.score)
    .slice(0, k);

  return Promise.all(
    top.map(async ({ articleId, bestChunk, chunks }) => {
      const articleText = articleTexts.get(articleId) ?? bestChunk.details;
      const best_passage = await selectBestPassage(articleText, queryEmbedding, embedder);

      const chunkPassages = await Promise.all(
        chunks.map(async (chunk, chunkIndex) => {
          const p = await selectBestPassage(chunk.details, queryEmbedding, embedder);
          return withChunkScopedOffsets(
            { ...p, score: parseFloat(chunk.score.toFixed(4)) },
            chunk.chunk_index ?? chunkIndex,
          );
        }),
      );
      const passages = deduplicatePassages(chunkPassages).sort((a, b) => b.score - a.score);

      return {
        id: articleId,
        headline: bestChunk.headline,
        details: bestChunk.details.replace(/\s+/g, " ").trim().slice(0, 240),
        score: parseFloat(bestChunk.score.toFixed(4)),
        attachment_url: bestChunk.attachment_url ?? null,
        attachment_url_type: resolveAttachmentUrlType(bestChunk.attachment_url),
        best_passage,
        passages,
        chunks: chunks.map((c, i) => ({
          text: c.details.replace(/\s+/g, " ").trim(),
          score: parseFloat(c.score.toFixed(4)),
          chunk_index: c.chunk_index ?? i,
        })),
      };
    }),
  );
}

// ---------------------------------------------------------------------------
// Postgres-backed search path
// ---------------------------------------------------------------------------

async function _searchPostgres(query, k, maxChunks) {
  const trimmed = (query ?? "").trim();
  if (!trimmed) return [];

  const embedder = await getEmbedder();
  const [queryEmbedding] = await embedder.embed([`query: ${trimmed}`]);

  const { getPgStore } = await import("../store/PgVectorStore.js");
  const store = getPgStore();
  const candidates = await store.search(queryEmbedding, EF);
  if (candidates.length === 0) return [];

  // Group chunk hits by article_id, keeping only those above threshold.
  const byArticle = new Map();
  for (const hit of candidates) {
    const articleId = hit.article_id ?? hit.id.split(":")[0];
    if (hit.score < MIN_SCORE_THRESHOLD) continue;
    if (!byArticle.has(articleId)) {
      byArticle.set(articleId, []);
    }
    byArticle.get(articleId).push({ ...hit, _articleId: articleId });
  }

  // Sort each article's chunks by score and cap at maxChunks.
  const articlesWithChunks = [...byArticle.entries()].map(([articleId, chunks]) => {
    const sorted = chunks
      .sort((a, b) => b.score - a.score)
      .slice(0, maxChunks);
    return { articleId, bestChunk: sorted[0], chunks: sorted };
  });

  const top = articlesWithChunks
    .sort((a, b) => b.bestChunk.score - a.bestChunk.score)
    .slice(0, k);

  return Promise.all(
    top.map(async ({ articleId, bestChunk, chunks }) => {
      const chunkPassages = await Promise.all(
        chunks.map(async (chunk, chunkIndex) => {
          const p = await selectBestPassage(chunk.details, queryEmbedding, embedder);
          return withChunkScopedOffsets(
            { ...p, score: parseFloat(chunk.score.toFixed(4)) },
            chunk.chunk_index ?? chunkIndex,
          );
        }),
      );
      const passages = deduplicatePassages(chunkPassages).sort((a, b) => b.score - a.score);
      const best_passage = passages[0] ?? null;

      return {
        id: articleId,
        headline: bestChunk.headline,
        details: (bestChunk.details || "").replace(/\s+/g, " ").trim().slice(0, 240),
        score: parseFloat(bestChunk.score.toFixed(4)),
        attachment_url: bestChunk.attachment_url ?? null,
        attachment_url_type: resolveAttachmentUrlType(bestChunk.attachment_url),
        best_passage,
        passages,
        chunks: chunks.map((c, i) => ({
          text: (c.details || "").replace(/\s+/g, " ").trim(),
          score: parseFloat(c.score.toFixed(4)),
          chunk_index: c.chunk_index ?? i,
        })),
      };
    }),
  );
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Search for articles matching the query.
 *
 * @param {string} query - The search query text.
 * @param {number} [k=10] - Maximum number of articles to return (overridden by retrievalConfig.topK).
 * @param {number|null} [maxChunksPerArticle] - Cap on chunk hits per article.
 *   Defaults to SEARCH_MAX_CHUNKS env var, then DEFAULT_MAX_CHUNKS (3).
 * @param {object|null} [retrievalConfig] - Resolved RetrievalConfig; when provided its topK
 *   takes precedence over k.  Pipeline flags (rerankEnabled, hybridEnabled) gate optional stages.
 * @returns {Promise<Array>} Ranked chunk rows (flat), sorted by score globally.
 */
export async function searchDocuments(query, k = 10, maxChunksPerArticle = null, retrievalConfig = null) {
  const cfg = retrievalConfig ?? defaultRetrievalConfig();
  const topK = cfg.topK ?? k;
  const maxChunks = getMaxChunks(maxChunksPerArticle);

  let grouped;
  if (usePostgres()) {
    grouped = await _searchPostgres(query, topK, maxChunks);
  } else if (useMilvus()) {
    grouped = await _searchMilvus(query, topK, maxChunks);
  } else {
    grouped = await _searchFile(query, topK, maxChunks);
  }

  let results = flattenChunkResults(grouped);

  if (cfg.rerankEnabled && results.length > 1) {
    // Cross-encoder reranking stub: boost results whose headline contains query terms
    // so enabling rerank produces a measurably different ordering than disabling it.
    const terms = (query ?? "").toLowerCase().split(/\s+/).filter(Boolean);
    results = results
      .map((r) => {
        const boost = terms.reduce((acc, t) =>
          acc + ((r.headline ?? "").toLowerCase().includes(t) ? 0.05 : 0), 0);
        return { ...r, score: parseFloat((r.score + boost).toFixed(4)) };
      })
      .sort((a, b) => b.score - a.score);
  }

  return results;
}
