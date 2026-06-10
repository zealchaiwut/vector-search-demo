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

  // Shape results: drop zero-score docs, sort, cap at k.
  return [...byDocId.values()]
    .filter((r) => r.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, k)
    .map((r) => ({
      doc_id: r.doc_id,
      title: r.title,
      snippet: r.text.replace(/\s+/g, " ").trim().slice(0, 240),
      score: parseFloat(r.score.toFixed(4)),
      attachment_name: `${r.doc_id}.txt`,
      download_url: `/download/${r.doc_id}`,
    }));
}
