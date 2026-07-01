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
import { useMilvus, milvusAddress, usePostgres } from "../data/backend.js";
import { flattenChunkResults } from "./flattenResults.js";
import { defaultRetrievalConfig } from "../config/retrieval.js";
import { mergeRrf } from "./rrf.js";
import { normalise } from "../text/normalise.js";

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

const _embedders = new Map();
async function getEmbedder(modelId) {
  const key = modelId || "__default__";
  if (!_embedders.has(key)) {
    const { createEmbedder } = await import("../embeddings/index.js");
    _embedders.set(key, await createEmbedder(modelId || undefined));
  }
  return _embedders.get(key);
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
  } catch (err) {
    console.warn("[search] Failed to load collection.json:", err?.message ?? err);
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

// Thai and other scripts without ASCII terminators produce single segments that
// span the entire chunk. When a segment exceeds this length, sub-window it so
// selectBestPassage() has meaningful candidate units to score.
const SENTENCE_MAX_CHARS = 200;
const SENTENCE_WINDOW_SIZE = 150;

function _subwindow(text, globalOffset) {
  const windows = [];
  let pos = 0;
  const len = text.length;
  while (pos < len) {
    const sliceEnd = Math.min(pos + SENTENCE_WINDOW_SIZE, len);
    const raw = text.slice(pos, sliceEnd);
    const trimmed = raw.trim();
    if (trimmed.length > 0) {
      const lead = raw.length - raw.trimStart().length;
      const start = globalOffset + pos + lead;
      windows.push({ text: trimmed, start, end: start + trimmed.length });
    }
    pos = sliceEnd;
  }
  return windows;
}

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

  // Fallback for Thai and other scripts: sub-window any segment that exceeds
  // SENTENCE_MAX_CHARS so selectBestPassage() can rank meaningful sub-units.
  const result = [];
  for (const s of sentences) {
    if (s.text.length > SENTENCE_MAX_CHARS) {
      result.push(..._subwindow(s.text, s.start));
    } else {
      result.push(s);
    }
  }
  return result;
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

/**
 * Select the sentence in docText that contains the greatest number of matched
 * query terms (lexical best-passage selection for keyword and hybrid modes).
 * Falls back to the first sentence when no terms match any sentence.
 *
 * @param {string} docText - Chunk or article text to scan.
 * @param {string[]} queryTerms - Lower-cased, pre-filtered query tokens.
 * @returns {{ text, start_offset, end_offset, context, match_count }}
 */
function selectBestPassageByTerms(docText, queryTerms) {
  const sentences = splitIntoSentences(docText);
  if (sentences.length === 0) {
    const trimmed = docText.trim();
    return {
      text: trimmed,
      start_offset: 0,
      end_offset: trimmed.length,
      context: { before: "", after: "" },
      match_count: 0,
    };
  }

  let bestIdx = 0;
  let bestCount = -1;
  for (let i = 0; i < sentences.length; i++) {
    const lower = sentences[i].text.toLowerCase();
    const count = queryTerms.reduce((n, t) => n + (lower.includes(t) ? 1 : 0), 0);
    if (count > bestCount) {
      bestCount = count;
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
    match_count: Math.max(bestCount, 0),
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
  if (candidates.length === 0) return [];

  // Group chunk hits by parent article ID (mirrors _searchFile / _searchPostgres).
  const byArticleId = new Map();
  for (const c of candidates) {
    const articleId = c.id.split(":")[0];
    if (!byArticleId.has(articleId)) {
      byArticleId.set(articleId, []);
    }
    byArticleId.get(articleId).push(c);
  }

  // Build full article text for best_passage (concatenate chunk details in order).
  const articleTexts = new Map();
  for (const [articleId, chunks] of byArticleId) {
    articleTexts.set(articleId, chunks.map((c) => c.details).join(" "));
  }

  // Sort chunks within each article by score, apply threshold + maxChunks cap.
  const top = [...byArticleId.entries()]
    .map(([articleId, chunks]) => {
      const sorted = chunks.slice().sort((a, b) => b.score - a.score);
      return { articleId, bestChunk: sorted[0], chunks: sorted.slice(0, maxChunks) };
    })
    .filter(({ bestChunk }) => bestChunk.score >= MIN_SCORE_THRESHOLD)
    .sort((a, b) => b.bestChunk.score - a.bestChunk.score)
    .slice(0, k);

  return Promise.all(
    top.map(async ({ articleId, bestChunk, chunks }) => {
      const articleText = articleTexts.get(articleId) ?? bestChunk.details;
      const best_passage = await selectBestPassage(articleText, queryEmbedding, embedder);

      const chunkPassages = await Promise.all(
        chunks.map(async (chunk) => {
          const chunkIndex = parseInt(chunk.id.split(":")[1] ?? "0", 10);
          const p = await selectBestPassage(chunk.details, queryEmbedding, embedder);
          return withChunkScopedOffsets(
            { ...p, score: parseFloat(chunk.score.toFixed(4)) },
            chunkIndex,
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
        chunks: chunks.map((c) => ({
          text: c.details.replace(/\s+/g, " ").trim(),
          score: parseFloat(c.score.toFixed(4)),
          chunk_index: parseInt(c.id.split(":")[1] ?? "0", 10),
        })),
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
// File-backed lexical search (term-frequency scoring)
// ---------------------------------------------------------------------------

/**
 * Simple term-frequency lexical scorer for the file-backed collection.
 * Returns flat chunk rows sorted by descending lexical score.
 *
 * @param {string} query
 * @param {number} k
 * @returns {Array<object>}
 */
export function _lexicalSearchFile(query, k = 10) {
  const rows = loadRows();
  if (rows.length === 0) return [];
  const trimmed = (query ?? "").trim();
  if (!trimmed) return [];

  const terms = trimmed.toLowerCase().split(/\s+/).filter(Boolean);
  if (terms.length === 0) return [];

  const scored = [];
  for (const row of rows) {
    const text = `${row.headline ?? ""} ${row.details ?? ""}`.toLowerCase();
    const totalLen = Math.max(text.length, 1);
    let lexicalScore = 0;
    for (const term of terms) {
      let count = 0;
      let pos = 0;
      while ((pos = text.indexOf(term, pos)) !== -1) {
        count++;
        pos += term.length;
      }
      lexicalScore += (count * term.length) / totalLen;
    }
    if (lexicalScore > 0) {
      const articleId = row.id.split(":")[0];
      const chunkIdx = row.chunk_index ?? parseInt((row.id.split(":")[1] ?? "0"), 10);
      const text_ = (row.details ?? "").replace(/\s+/g, " ").trim();
      scored.push({
        id: articleId,
        article_id: articleId,
        chunk_index: chunkIdx,
        headline: row.headline,
        text: text_,
        details: text_.slice(0, 240),
        score: lexicalScore,
        attachment_url: row.attachment_url ?? null,
        attachment_url_type: resolveAttachmentUrlType(row.attachment_url),
        best_passage: { text: text_, start_offset: 0, end_offset: text_.length, context: { before: "", after: "" }, score: lexicalScore },
        passages: [{ text: text_, start_offset: 0, end_offset: text_.length, context: { before: "", after: "" }, score: lexicalScore }],
        chunks: [{ text: text_, score: lexicalScore, chunk_index: chunkIdx }],
      });
    }
  }

  return scored.sort((a, b) => b.score - a.score).slice(0, k);
}

// ---------------------------------------------------------------------------
// Postgres-backed search path
// ---------------------------------------------------------------------------

async function _perModelCandidates(store, queryVec, modelId, limit) {
  // Per-model dense vectors live in chunk_embeddings (real[], dimension-agnostic).
  // Fetch this model's vectors joined to chunk metadata and score cosine in JS
  // (embeddings are L2-normalised, so dot product == cosine).
  const res = await store._query(
    `SELECT ce.chunk_id AS id, a.article_id, a.headline, a.details,
            a.attachment_url, a.chunk_index, ce.vector
       FROM chunk_embeddings ce
       JOIN articles a ON a.id = ce.chunk_id
      WHERE ce.model_id = $1`,
    [modelId],
  );
  return res.rows
    .map((r) => ({
      id: r.id,
      article_id: r.article_id,
      headline: r.headline,
      details: r.details,
      attachment_url: r.attachment_url,
      chunk_index: r.chunk_index,
      score: dotProduct(queryVec, r.vector),
    }))
    .sort((a, b) => b.score - a.score)
    .slice(0, limit);
}

async function _searchPostgres(query, k, maxChunks, modelId = null) {
  const trimmed = (query ?? "").trim();
  if (!trimmed) return [];

  const embedder = await getEmbedder(modelId);
  const [queryEmbedding] = await embedder.embed([`query: ${trimmed}`]);

  const { getPgStore } = await import("../store/PgVectorStore.js");
  const store = getPgStore();
  // When a model is explicitly selected, rank against that model's per-chunk
  // vectors in chunk_embeddings; otherwise use the default articles.embedding.
  const candidates = modelId
    ? await _perModelCandidates(store, queryEmbedding, modelId, EF)
    : await store.search(queryEmbedding, EF);
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
// Debug explain utilities
// ---------------------------------------------------------------------------

function _explainKey(result) {
  return `${result.id}:${result.chunk_index ?? 0}`;
}

/**
 * Record a pipeline stage into the per-result explain map.
 * Each stage entry captures the result's score and rank at that stage,
 * plus the rank change (rankDelta) from the immediately prior stage and
 * the wall-clock time spent in the stage (latencyMs).
 *
 * @param {Map} explainMap - keyed by _explainKey(result)
 * @param {Array} sortedResults - results sorted by score at this stage
 * @param {string} stageName - e.g. 'dense', 'lexical', 'rrf', 'rerank'
 * @param {number} latencyMs - ms spent in this stage
 */
function _recordExplainStage(explainMap, sortedResults, stageName, latencyMs) {
  sortedResults.forEach((r, idx) => {
    const key = _explainKey(r);
    const stages = explainMap.get(key) ?? [];
    const prevStage = stages[stages.length - 1];
    stages.push({
      stage: stageName,
      score: r.score,
      rank: idx + 1,
      rankDelta: prevStage ? (idx + 1) - prevStage.rank : 0,
      latencyMs: parseFloat(latencyMs.toFixed(2)),
    });
    explainMap.set(key, stages);
  });
}

/**
 * Enforce the per-article chunk cap on a flat, score-sorted result list.
 * The dense stage caps chunks per article during grouping, but lexical + RRF
 * fusion can reintroduce more chunks of the same article, so the final list
 * must be re-capped. Input order is preserved (already ranked), so this keeps
 * the top `maxChunks` chunks of each article.
 */
function capChunksPerArticle(results, maxChunks) {
  const perArticle = new Map();
  const kept = [];
  for (const r of results) {
    const aid = r.article_id ?? r.id;
    const n = perArticle.get(aid) ?? 0;
    if (n >= maxChunks) continue;
    perArticle.set(aid, n + 1);
    kept.push(r);
  }
  return kept;
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
 * @param {boolean} [debug=false] - When true, attaches an `explain` block to each result
 *   containing per-stage scores, ranks, rank deltas, and latency.  Stages that did not run
 *   are omitted entirely.  No explain overhead is incurred when debug is false.
 * @returns {Promise<Array>} Ranked chunk rows (flat), sorted by score globally.
 *   Each row optionally contains `explain: ExplainStage[]` when debug=true.
 */
export async function searchDocuments(query, k = 10, maxChunksPerArticle = null, retrievalConfig = null, debug = false) {
  const cfg = retrievalConfig ?? defaultRetrievalConfig();
  const topK = cfg.topK ?? k;
  const maxChunks = getMaxChunks(maxChunksPerArticle);

  // Normalise query text before embedding (same module used at ingest time)
  const normalisedQuery = normalise(query, cfg.textNormalisationEnabled);

  // When reranking is enabled, retrieve a larger candidate pool before reranking.
  const rerankCandidateCount = cfg.rerankCandidateCount ?? 50;
  const retrievalK = cfg.rerankEnabled ? Math.max(topK, rerankCandidateCount) : topK;

  // --- Stage 1: Dense retrieval ---
  const denseT0 = performance.now();
  const modelId = cfg.modelId ?? null;
  let grouped;
  if (usePostgres()) {
    grouped = await _searchPostgres(normalisedQuery, retrievalK, maxChunks, modelId);
  } else if (useMilvus()) {
    grouped = await _searchMilvus(normalisedQuery, retrievalK, maxChunks);
  } else {
    grouped = await _searchFile(normalisedQuery, retrievalK, maxChunks);
  }
  let results = flattenChunkResults(grouped);
  const denseLatencyMs = performance.now() - denseT0;

  // Build explain map only when debug is requested (zero overhead otherwise).
  const explainMap = debug ? new Map() : null;
  if (debug) {
    _recordExplainStage(explainMap, results, "dense", denseLatencyMs);
  }

  // --- Stage 2 & 3: Lexical scoring + RRF fusion (hybrid pipeline) ---
  if (cfg.hybridEnabled) {
    const rrfK = cfg.rrfK ?? 60;

    // Run lexical search on the appropriate backend.
    const lexicalT0 = performance.now();
    let lexicalResults = [];
    try {
      if (usePostgres()) {
        const { getPgStore } = await import("../store/PgVectorStore.js");
        const { searchLexical } = await import("../core/lexical/index.js");
        const store = getPgStore();
        const lexRows = await searchLexical(store, normalisedQuery, topK);
        lexicalResults = lexRows.map((row) => {
          const text = (row.details ?? "").replace(/\s+/g, " ").trim();
          return {
            id: row.id,
            article_id: row.id,
            chunk_index: row.chunk_index ?? 0,
            headline: row.headline,
            text,
            details: text.slice(0, 240),
            score: row.lexical_score,
            attachment_url: row.attachment_url ?? null,
            attachment_url_type: resolveAttachmentUrlType(row.attachment_url),
            best_passage: { text, start_offset: 0, end_offset: text.length, context: { before: "", after: "" }, score: row.lexical_score },
            passages: [{ text, start_offset: 0, end_offset: text.length, context: { before: "", after: "" }, score: row.lexical_score }],
            chunks: [{ text, score: row.lexical_score, chunk_index: row.chunk_index ?? 0 }],
          };
        });
      } else if (!useMilvus()) {
        // File-backed backend: use term-frequency lexical scorer.
        lexicalResults = _lexicalSearchFile(normalisedQuery, topK);
      }
      // Milvus has no native lexical path; lexicalResults stays [].
    } catch {
      lexicalResults = [];
    }
    const lexicalLatencyMs = performance.now() - lexicalT0; // stub — no real computation on Milvus path; will reflect BM25 cost when implemented

    if (debug) {
      _recordExplainStage(explainMap, lexicalResults, "lexical", lexicalLatencyMs);
    }

    // RRF fusion: merge dense + lexical lists.
    const denseResultCount = results.length;
    const rrfT0 = performance.now();
    const fused = mergeRrf(results, lexicalResults, rrfK);
    results = fused.slice(0, topK);
    const rrfLatencyMs = performance.now() - rrfT0;

    if (debug) {
      _recordExplainStage(explainMap, results, "rrf", rrfLatencyMs);
      // Fill in missing dense/lexical stages for results that appeared in only one list.
      for (const r of results) {
        const key = _explainKey(r);
        const stages = explainMap.get(key) ?? [];
        if (!stages.some((s) => s.stage === "lexical")) {
          const rrfIdx = stages.findIndex((s) => s.stage === "rrf");
          const miss = { stage: "lexical", score: 0, rank: lexicalResults.length + 1, rankDelta: 0, latencyMs: parseFloat(lexicalLatencyMs.toFixed(2)) };
          if (rrfIdx >= 0) stages.splice(rrfIdx, 0, miss);
          else stages.push(miss);
          explainMap.set(key, stages);
        }
        if (!stages.some((s) => s.stage === "dense")) {
          const lexIdx = stages.findIndex((s) => s.stage === "lexical");
          const miss = { stage: "dense", score: 0, rank: denseResultCount + 1, rankDelta: 0, latencyMs: parseFloat(denseLatencyMs.toFixed(2)) };
          if (lexIdx >= 0) stages.splice(lexIdx, 0, miss);
          else stages.unshift(miss);
          explainMap.set(key, stages);
        }
      }
    }
    // dense_rank, lexical_rank, fused_score are always set by mergeRrf on hybrid results.
  }

  // --- Stage 4: Cross-encoder reranking ---
  if (cfg.rerankEnabled && results.length > 0) {
    const rerankT0 = performance.now();

    const { createReranker } = await import("../rerank/index.js");
    const reranker = createReranker();
    const chunks = results.map((r) => r.details ?? r.text ?? "");
    const rerankScores = await reranker.rerank(normalisedQuery, chunks);
    const reranked = results
      .map((result, idx) => ({
        result: { ...result, score: parseFloat((rerankScores[idx] ?? result.score).toFixed(6)) },
        rerankScore: parseFloat((rerankScores[idx] ?? result.score).toFixed(6)),
        preRerankRank: idx + 1,
      }))
      .sort((a, b) => b.rerankScore - a.rerankScore)
      .map((item, idx) => ({ ...item, postRerankRank: idx + 1 }));

    // Drop results the cross-encoder scored as irrelevant (<= 0) — these are
    // junk/placeholder docs that dense retrieval surfaced on weak similarity but
    // the reranker correctly rejects. Slice to topK after filtering.
    const rerankedTop = reranked.filter(({ rerankScore }) => rerankScore > 0).slice(0, topK);

    if (debug) {
      const rerankLatencyMs = performance.now() - rerankT0;
      rerankedTop.forEach(({ result, rerankScore, preRerankRank, postRerankRank }) => {
        const key = _explainKey(result);
        const stages = explainMap.get(key) ?? [];
        const prevStage = stages[stages.length - 1];
        stages.push({
          stage: "rerank",
          score: result.score,
          rank: postRerankRank,
          rankDelta: prevStage ? postRerankRank - prevStage.rank : 0,
          latencyMs: parseFloat(rerankLatencyMs.toFixed(2)),
          rerankScore,
          preRerankRank,
          postRerankRank,
        });
        explainMap.set(key, stages);
      });
    }

    results = rerankedTop.map(({ result }) => result);
  } else if (cfg.rerankEnabled) {
    // No candidates to rerank; just return empty.
    results = [];
  }

  // For hybrid mode, re-select each result's passage by term count rather than
  // semantic cosine similarity so the surfaced passage contains the most matched
  // query terms (AC3 of issue #188).
  if (cfg.hybridEnabled) {
    const queryTerms = normalisedQuery.toLowerCase().split(/\s+/).filter((t) => t.length >= 2);
    results = results.map((r) => {
      const text = r.text || r.details || "";
      if (!text || queryTerms.length === 0) return r;
      const newPassage = selectBestPassageByTerms(text, queryTerms);
      return {
        ...r,
        passages: [{ ...(r.passages?.[0] ?? {}), ...newPassage }],
        best_passage: newPassage,
      };
    });
  }

  // Enforce the per-article chunk cap on the final flat list. The dense stage
  // caps during grouping, but lexical + RRF fusion can reintroduce more chunks
  // of the same article, so re-cap here so no article shows more than maxChunks.
  results = capChunksPerArticle(results, maxChunks);

  // Attach explain blocks to each result (only when debug=true).
  if (debug) {
    results = results.map((r) => ({
      ...r,
      explain: explainMap.get(_explainKey(r)) ?? [],
    }));
  }

  return results;
}
