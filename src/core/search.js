/**
 * Core search logic for vector-search-demo.
 *
 * Embeds the query with the MiniLM model (same model used at ingest), then
 * ranks chunks by COSINE similarity against their stored embeddings.
 * Uses EF=64 over-fetching and per-article chunk collapsing before returning
 * the top-k shaped results.
 *
 * When MILVUS_HOST is set, queries the Milvus 'documents' collection via
 * vector search. Otherwise falls back to the file-backed collection.json.
 *
 * Search depends on ingest: with an empty/absent collection it returns [].
 */

import { readFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { createEmbedder } from "../embeddings/index.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const COLLECTION_PATH = join(__dirname, "..", "..", "collection.json");
const COLLECTION_NAME = "documents";

const EF = 64;

let _embedder = null;
async function getEmbedder() {
  if (!_embedder) _embedder = await createEmbedder();
  return _embedder;
}

// ---------------------------------------------------------------------------
// File-backed collection access
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

// ---------------------------------------------------------------------------
// TF-IDF helpers — used only for best_passage sentence scoring
// ---------------------------------------------------------------------------

function tokenize(text) {
  return text.toLowerCase().match(/\b[a-z0-9]+\b/g) ?? [];
}

function buildIDF(texts) {
  const N = texts.length;
  const df = new Map();
  for (const text of texts) {
    for (const t of new Set(tokenize(text))) {
      df.set(t, (df.get(t) ?? 0) + 1);
    }
  }
  const idf = new Map();
  for (const [t, count] of df) {
    idf.set(t, Math.log((N + 1) / (count + 1)) + 1);
  }
  return idf;
}

function tfidfEmbed(text, idf) {
  const tokens = tokenize(text);
  if (tokens.length === 0) return null;
  const tf = new Map();
  for (const t of tokens) tf.set(t, (tf.get(t) ?? 0) + 1);
  const vec = new Map();
  for (const [t, count] of tf) {
    vec.set(t, (count / tokens.length) * (idf.get(t) ?? Math.log(2)));
  }
  let norm = 0;
  for (const v of vec.values()) norm += v * v;
  norm = Math.sqrt(norm);
  if (norm === 0) return null;
  const out = new Map();
  for (const [t, v] of vec) out.set(t, v / norm);
  return out;
}

function sparseDot(a, b) {
  if (!a || !b) return 0;
  let dot = 0;
  for (const [t, va] of a) {
    const vb = b.get(t);
    if (vb !== undefined) dot += va * vb;
  }
  return dot;
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
      // Boundary: end of string or next non-space char is uppercase
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

function selectBestPassage(docText, queryVec, idf) {
  const sentences = splitIntoSentences(docText);
  if (sentences.length === 0) {
    const trimmed = docText.trim();
    return { text: trimmed, start_offset: 0, end_offset: trimmed.length };
  }

  let best = sentences[0];
  let bestScore = -1;

  for (const sentence of sentences) {
    const score = sparseDot(queryVec, tfidfEmbed(sentence.text, idf));
    if (score > bestScore) {
      bestScore = score;
      best = sentence;
    }
  }

  return { text: best.text, start_offset: best.start, end_offset: best.end };
}

// ---------------------------------------------------------------------------
// Shared result shaping
// ---------------------------------------------------------------------------

function shapeResults(candidates, rows, trimmed, k) {
  const articleTexts = new Map();
  for (const row of rows) {
    const aid = row.id.split(":")[0];
    if (!articleTexts.has(aid)) {
      articleTexts.set(aid, row.details);
    } else {
      articleTexts.set(aid, articleTexts.get(aid) + " " + row.details);
    }
  }

  const idf = buildIDF(rows.map((r) => `${r.headline} ${r.details}`));
  const queryVecSparse = tfidfEmbed(trimmed, idf);

  return [...candidates.values()]
    .filter((r) => r.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, k)
    .map((r) => {
      const articleText = articleTexts.get(r.articleId) ?? r.details;
      const best_passage = selectBestPassage(articleText, queryVecSparse, idf);
      return {
        id: r.articleId,
        headline: r.headline,
        details: r.details.replace(/\s+/g, " ").trim().slice(0, 240),
        score: parseFloat(r.score.toFixed(4)),
        attachment_url: r.attachment_url,
        best_passage,
      };
    });
}

// ---------------------------------------------------------------------------
// Milvus-backed search
// ---------------------------------------------------------------------------

async function _searchMilvus(query, k) {
  const { MilvusClient } = await import("@zilliz/milvus2-sdk-node");
  const host = process.env.MILVUS_HOST;
  const port = process.env.MILVUS_PORT || "19530";
  const client = new MilvusClient({ address: `${host}:${port}` });

  const trimmed = (query ?? "").trim();
  if (!trimmed) return [];

  const embedder = await getEmbedder();
  const [queryEmbedding] = await embedder.embed([trimmed]);

  let hits;
  try {
    const searchResult = await client.search({
      collection_name: COLLECTION_NAME,
      data: [queryEmbedding],
      anns_field: "embedding",
      limit: EF,
      output_fields: ["id", "headline", "details", "attachment_url"],
      params: { ef: EF },
    });
    hits = searchResult.results || [];
  } catch {
    return [];
  }

  if (hits.length === 0) return [];

  // Collapse by article ID (keep best score per article)
  const byArticleId = new Map();
  for (const hit of hits) {
    const articleId = hit.id.split(":")[0];
    if (!byArticleId.has(articleId) || hit.score > byArticleId.get(articleId).score) {
      byArticleId.set(articleId, {
        articleId,
        id: hit.id,
        headline: hit.headline,
        details: hit.details,
        attachment_url: hit.attachment_url,
        score: hit.score,
      });
    }
  }

  // Use hit rows directly for best_passage (avoids extra Milvus round-trips)
  const rows = hits.map((h) => ({
    id: h.id,
    headline: h.headline,
    details: h.details,
    attachment_url: h.attachment_url,
  }));

  return shapeResults(byArticleId, rows, trimmed, k);
}

// ---------------------------------------------------------------------------
// File-backed search
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

  const byArticleId = new Map();
  for (const c of candidates) {
    if (!byArticleId.has(c.articleId) || c.score > byArticleId.get(c.articleId).score) {
      byArticleId.set(c.articleId, c);
    }
  }

  return shapeResults(byArticleId, rows, trimmed, k);
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

// Returns a Promise — call sites must await.
export function searchDocuments(query, k = 10) {
  if (process.env.MILVUS_HOST) {
    return _searchMilvus(query, k);
  }
  return _searchFile(query, k);
}
