/**
 * Core search logic for vector-search-demo.
 *
 * Milvus backend (DATA_BACKEND=milvus): embeds the query with MiniLM, runs ANN
 * search via Milvus COSINE similarity, collapses chunks to articles, extracts
 * best passage.
 *
 * Mock backend (DATA_BACKEND=mock, the default): loads rows from collection.json
 * and ranks by cosine similarity (same MiniLM embeddings, local computation).
 *
 * See ../data/backend.js for the selector.
 *
 * Search depends on ingest: empty or absent data returns [].
 */

import { readFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { createEmbedder } from "../embeddings/index.js";
import { useMilvus, milvusAddress, usePostgres } from "../data/backend.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const COLLECTION_PATH = join(__dirname, "..", "..", "collection.json");

const EF = 64;
const MAX_CHUNKS_PER_ARTICLE = 3;
const MIN_SCORE_THRESHOLD = 0.1;

let _embedder = null;
async function getEmbedder() {
  if (!_embedder) _embedder = await createEmbedder();
  return _embedder;
}

// ---------------------------------------------------------------------------
// Attachment URL type discriminator
// ---------------------------------------------------------------------------

/**
 * Determines the attachment URL type for a given URL string.
 * Returns "local" for paths served under /download/, "external" for http(s)
 * URLs, and null when no URL is provided.
 *
 * @param {string|null|undefined} url - The attachment URL to classify.
 * @returns {"external" | "local" | null}
 */
function resolveAttachmentUrlType(url) {
  if (!url) return null;
  if (url.startsWith("/download/")) return "local";
  if (url.startsWith("http://") || url.startsWith("https://")) return "external";
  return "external";
}

// ---------------------------------------------------------------------------
// File-backed collection access (fallback when MILVUS_HOST not set)
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
// Dense vector cosine similarity (dot product on pre-normalised vectors)
// ---------------------------------------------------------------------------

function dotProduct(a, b) {
  let sum = 0;
  for (let i = 0; i < a.length; i++) sum += a[i] * b[i];
  return sum;
}

// MiniLM embeddings are L2-normalised, so cosine similarity is just the dot
// product. Best-passage selection uses the same dense embeddings as ranking,
// so the highlighted passage reflects semantic closeness — not keyword overlap.
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

// How many sentences of surrounding context to return on each side of the hit.
const CONTEXT_SENTENCES = 2;

// Pick the single most relevant sentence by embedding each sentence and taking
// the highest cosine similarity to the query embedding (same model as ranking).
// Also returns the neighboring sentences (before/after) so the UI can show the
// hit in context — a semantic match rarely lands on a standalone sentence.
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
// Passage deduplication — removes passages whose start_offset is within
// OFFSET_PROXIMITY characters of a passage already in the output list.
// ---------------------------------------------------------------------------

const OFFSET_PROXIMITY = 20;

function deduplicatePassages(passages) {
  const seen = [];
  return passages.filter((p) => {
    const isDup = seen.some(
      (s) => Math.abs(s.start_offset - p.start_offset) < OFFSET_PROXIMITY
    );
    if (!isDup) seen.push(p);
    return !isDup;
  });
}

// ---------------------------------------------------------------------------
// Milvus-backed search path (used when DATA_BACKEND=milvus / MILVUS_HOST set)
// ---------------------------------------------------------------------------

async function _searchMilvus(query, k) {
  const trimmed = (query ?? "").trim();
  if (!trimmed) return [];

  const embedder = await getEmbedder();
  const [queryEmbedding] = await embedder.embed([trimmed]);

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
      };
    })
  );
}

// ---------------------------------------------------------------------------
// File-backed search path (fallback when MILVUS_HOST not set)
// ---------------------------------------------------------------------------

async function _searchFile(query, k) {
  const rows = loadRows();
  if (rows.length === 0) return [];

  const trimmed = (query ?? "").trim();
  if (!trimmed) return [];

  const embedder = await getEmbedder();
  const [queryEmbedding] = await embedder.embed([trimmed]);

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

  // Group chunks by article_id
  const byArticleId = new Map();
  for (const c of candidates) {
    if (!byArticleId.has(c.articleId)) {
      byArticleId.set(c.articleId, []);
    }
    byArticleId.get(c.articleId).push(c);
  }

  // Build full article text for backward-compat best_passage computation
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
      chunks: chunks.slice(0, MAX_CHUNKS_PER_ARTICLE),
    }))
    .sort((a, b) => b.bestChunk.score - a.bestChunk.score)
    .slice(0, k);

  return Promise.all(
    top.map(async ({ articleId, bestChunk, chunks }) => {
      const articleText = articleTexts.get(articleId) ?? bestChunk.details;
      // best_passage computed from full article text for backward compat
      const best_passage = await selectBestPassage(articleText, queryEmbedding, embedder);

      // passages: one entry per top-scoring chunk
      const chunkPassages = await Promise.all(
        chunks.map(async (chunk) => {
          const p = await selectBestPassage(chunk.details, queryEmbedding, embedder);
          return { ...p, score: parseFloat(chunk.score.toFixed(4)) };
        })
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
      };
    })
  );
}

// ---------------------------------------------------------------------------
// Postgres-backed search path (DB_BACKEND=postgres)
// ---------------------------------------------------------------------------

async function _searchPostgres(query, k) {
  const trimmed = (query ?? "").trim();
  if (!trimmed) return [];

  const embedder = await getEmbedder();
  const [queryEmbedding] = await embedder.embed([trimmed]);

  const { getPgStore } = await import("../store/PgVectorStore.js");
  const store = getPgStore();
  // Fetch more candidates (EF) so chunk-level ANN has enough to collapse to k articles.
  const candidates = await store.search(queryEmbedding, EF);
  if (candidates.length === 0) return [];

  // Group chunk hits by article_id, keeping top MAX_CHUNKS_PER_ARTICLE above threshold.
  const byArticle = new Map();
  for (const hit of candidates) {
    const articleId = hit.article_id ?? hit.id.split(":")[0];
    if (hit.score < MIN_SCORE_THRESHOLD) continue;
    if (!byArticle.has(articleId)) {
      byArticle.set(articleId, []);
    }
    byArticle.get(articleId).push({ ...hit, _articleId: articleId });
  }

  // Sort each article's chunks by score and cap at MAX_CHUNKS_PER_ARTICLE.
  const articlesWithChunks = [...byArticle.entries()].map(([articleId, chunks]) => {
    const sorted = chunks.sort((a, b) => b.score - a.score).slice(0, MAX_CHUNKS_PER_ARTICLE);
    return { articleId, bestChunk: sorted[0], chunks: sorted };
  });

  const top = articlesWithChunks
    .sort((a, b) => b.bestChunk.score - a.bestChunk.score)
    .slice(0, k);

  return Promise.all(
    top.map(async ({ articleId, bestChunk, chunks }) => {
      // passages: one entry per top-scoring chunk
      const chunkPassages = await Promise.all(
        chunks.map(async (chunk) => {
          const p = await selectBestPassage(chunk.details, queryEmbedding, embedder);
          return { ...p, score: parseFloat(chunk.score.toFixed(4)) };
        })
      );
      const passages = deduplicatePassages(chunkPassages).sort((a, b) => b.score - a.score);
      const best_passage = passages[0] ?? null;

      return {
        id: articleId,
        headline: bestChunk.headline,
        details: bestChunk.details.replace(/\s+/g, " ").trim().slice(0, 240),
        score: parseFloat(bestChunk.score.toFixed(4)),
        attachment_url: bestChunk.attachment_url ?? null,
        attachment_url_type: resolveAttachmentUrlType(bestChunk.attachment_url),
        best_passage,
        passages,
      };
    })
  );
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

async function _searchImpl(query, k) {
  if (usePostgres()) {
    return _searchPostgres(query, k);
  }
  if (useMilvus()) {
    return _searchMilvus(query, k);
  }
  return _searchFile(query, k);
}

// Returns a Promise — call sites must await.
export function searchDocuments(query, k = 10) {
  return _searchImpl(query, k);
}
