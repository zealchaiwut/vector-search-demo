/**
 * Core search logic for vector-search-demo.
 *
 * Reads the ingested, file-backed collection (collection.json, produced by
 * `ingest`), rebuilds a TF-IDF space over the stored chunk texts, embeds the
 * query into that same space, and ranks documents by cosine similarity with
 * ef-style over-fetching and per-document chunk collapsing.
 *
 * Search depends on ingest: with an empty/absent collection it returns [].
 */

import { readFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const COLLECTION_PATH = join(__dirname, "..", "..", "collection.json");

const EF = 64;

// ---------------------------------------------------------------------------
// Collection access — load the ingested chunk rows from disk
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
// TF-IDF embedding + cosine similarity (sparse, Map-backed)
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

function embed(text, idf) {
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

function cosineSimilarity(a, b) {
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

  // Remaining text without terminal punctuation
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
    const score = cosineSimilarity(queryVec, embed(sentence.text, idf));
    if (score > bestScore) {
      bestScore = score;
      best = sentence;
    }
  }

  return { text: best.text, start_offset: best.start, end_offset: best.end };
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export function searchDocuments(query, k = 10) {
  const rows = loadRows();
  if (rows.length === 0) return [];

  // Build the TF-IDF space over the ingested chunk corpus, then embed query.
  const idf = buildIDF(rows.map((r) => `${r.title} ${r.text}`));
  const queryVec = embed(query, idf);
  if (!queryVec) return [];

  // Score every chunk by cosine similarity in the shared space.
  const scored = rows.map((row) => ({
    doc_id: row.doc_id,
    title: row.title,
    text: row.text,
    score: cosineSimilarity(queryVec, embed(`${row.title} ${row.text}`, idf)),
  }));

  // Over-fetch the top EF chunks before collapsing to documents.
  const candidates = scored.sort((a, b) => b.score - a.score).slice(0, EF);

  // Collapse: keep the best-scoring chunk per doc_id.
  const byDocId = new Map();
  for (const c of candidates) {
    if (!byDocId.has(c.doc_id) || c.score > byDocId.get(c.doc_id).score) {
      byDocId.set(c.doc_id, c);
    }
  }

  // Build full doc_text per doc_id (chunk texts joined in collection order).
  const docTexts = new Map();
  for (const row of rows) {
    if (!docTexts.has(row.doc_id)) {
      docTexts.set(row.doc_id, row.text);
    } else {
      docTexts.set(row.doc_id, docTexts.get(row.doc_id) + " " + row.text);
    }
  }

  // Shape results: drop zero-score docs, sort, cap at k.
  return [...byDocId.values()]
    .filter((r) => r.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, k)
    .map((r) => {
      const docText = docTexts.get(r.doc_id) ?? r.text;
      const best_passage = selectBestPassage(docText, queryVec, idf);
      return {
        doc_id: r.doc_id,
        title: r.title,
        snippet: r.text.replace(/\s+/g, " ").trim().slice(0, 240),
        score: parseFloat(r.score.toFixed(4)),
        attachment_name: `${r.doc_id}.txt`,
        download_url: `/download/${r.doc_id}`,
        best_passage,
      };
    });
}
