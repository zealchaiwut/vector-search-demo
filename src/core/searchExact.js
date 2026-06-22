/**
 * Keyword (exact) search using Postgres.
 *
 * English/Latin queries use FTS (plainto_tsquery + ts_rank over tsvector).
 * Thai and other non-Latin scripts use case-insensitive substring matching
 * (Postgres english FTS does not tokenize unspaced Thai text).
 *
 * Only functional when DB_BACKEND=postgres; returns [] for other backends.
 *
 * Response shape per result (flat — one row per chunk):
 *   { id, article_id, chunk_index, headline, text, score, attachment_url, passages }
 */

import { usePostgres } from "../data/backend.js";
import { getPgStore } from "../store/PgVectorStore.js";
import { flattenChunkResults } from "../search/flattenResults.js";

const MAX_CHUNKS_PER_ARTICLE = 3;
const TS_HEADLINE_OPTS =
  "MaxWords=35, MinWords=15, ShortWord=3, HighlightAll=FALSE, MaxFragments=1";
const SNIPPET_CONTEXT = 80;

/** Thai script — english FTS cannot match these queries reliably. */
const THAI_RE = /[\u0E00-\u0E7F]/;

/** @param {string} html */
function stripHtml(html) {
  return (html ?? "").replace(/<[^>]+>/g, "");
}

/** @param {string} html */
function sanitizeHeadlineHtml(html) {
  if (!html) return "";
  return html
    .replace(/<b>/gi, '<strong class="kw">')
    .replace(/<\/b>/gi, "</strong>")
    .replace(/<(?!\/?strong\b)[^>]*>/gi, "");
}

/** Escape %, _, and \\ for use in ILIKE ... ESCAPE '\\'. */
function escapeLikePattern(text) {
  return text.replace(/[%_\\]/g, "\\$&");
}

/** @param {string} haystack @param {string} needle */
function findMatchIndex(haystack, needle) {
  return haystack.toLocaleLowerCase("th-TH").indexOf(needle.toLocaleLowerCase("th-TH"));
}

/** @param {string} text */
function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]),
  );
}

/**
 * Build a plain + HTML snippet around the first case-insensitive match.
 * @param {string} text
 * @param {string} query
 */
function excerptWithHighlight(text, query) {
  const idx = findMatchIndex(text, query);
  if (idx === -1) {
    const plain = text.slice(0, 160);
    return { text: plain, html: escapeHtml(plain) };
  }
  const start = Math.max(0, idx - SNIPPET_CONTEXT);
  const end = Math.min(text.length, idx + query.length + SNIPPET_CONTEXT);
  const slice = text.slice(start, end);
  const rel = findMatchIndex(slice, query);
  const prefix = start > 0 ? "…" : "";
  const suffix = end < text.length ? "…" : "";
  const before = escapeHtml(slice.slice(0, rel));
  const match = escapeHtml(slice.slice(rel, rel + query.length));
  const after = escapeHtml(slice.slice(rel + query.length));
  return {
    text: prefix + slice + suffix,
    html: `${prefix}${before}<strong class="kw">${match}</strong>${after}${suffix}`,
  };
}

/** @param {string} text @param {string} query */
function substringScore(text, query) {
  const idx = findMatchIndex(text, query);
  if (idx === -1) return 0;
  // Prefer earlier matches; keep score in (0, 1].
  return 1 - Math.min(idx, 5000) / 5001;
}

/**
 * @param {Array<{ id: string, headline: string, attachment_url: string|null, chunk_index: number, details: string, text: string, html: string, score: number }>} rows
 * @param {number} k
 */
function groupChunkRows(rows, k) {
  /** @type {Map<string, { id: string, headline: string, attachment_url: string|null, chunks: object[] }>} */
  const byArticle = new Map();

  for (const row of rows) {
    if (!byArticle.has(row.id)) {
      byArticle.set(row.id, {
        id: row.id,
        headline: row.headline,
        attachment_url: row.attachment_url ?? null,
        chunks: [],
      });
    }
    const entry = byArticle.get(row.id);
    if (entry.chunks.length >= MAX_CHUNKS_PER_ARTICLE) continue;
    entry.chunks.push({
      text: row.text,
      html: row.html,
      score: row.score,
      chunk_index: row.chunk_index,
      details: row.details,
    });
  }

  return [...byArticle.values()]
    .filter((a) => a.chunks.length > 0)
    .map((a) => {
      const sorted = a.chunks.sort((x, y) => y.score - x.score);
      const passages = sorted.map((c) => ({
        text: c.text,
        html: c.html,
        score: c.score,
        chunk_index: c.chunk_index,
      }));
      const best = passages[0];
      return {
        id: a.id,
        headline: a.headline,
        details: sorted[0].details,
        score: best.score,
        attachment_url: a.attachment_url,
        best_passage: best.text,
        passages,
      };
    })
    .sort((a, b) => b.score - a.score)
    .slice(0, k);
}

/**
 * @param {import("../store/PgVectorStore.js").PgVectorStore} store
 * @param {string} query
 * @param {number} k
 */
async function searchExactFts(store, query, k) {
  const result = await store._query(
    `SELECT article_id AS id,
            chunk_index,
            headline,
            details,
            ts_rank(ts, plainto_tsquery('english', $1)) AS score,
            attachment_url,
            ts_headline(
              'english',
              coalesce(headline, '') || ' ' || coalesce(details, ''),
              plainto_tsquery('english', $1),
              $2
            ) AS snippet
     FROM articles
     WHERE ts @@ plainto_tsquery('english', $1)
     ORDER BY article_id, ts_rank(ts, plainto_tsquery('english', $1)) DESC`,
    [query, TS_HEADLINE_OPTS],
  );

  const rows = result.rows.map((row) => {
    const body = `${row.headline ?? ""} ${row.details ?? ""}`.trim();
    const html = sanitizeHeadlineHtml(row.snippet);
    const headlineText = stripHtml(row.snippet);
    const hasQuery = findMatchIndex(body, query) !== -1;
    const excerpt = hasQuery ? excerptWithHighlight(body, query) : { text: headlineText, html };
    return {
      id: row.id,
      headline: row.headline,
      attachment_url: row.attachment_url,
      chunk_index: row.chunk_index,
      details: row.details,
      text: excerpt.text,
      html: excerpt.html || html,
      score: parseFloat(row.score),
    };
  });

  return groupChunkRows(rows, k);
}

/**
 * Case-insensitive substring search for Thai / unspaced scripts.
 * @param {import("../store/PgVectorStore.js").PgVectorStore} store
 * @param {string} query
 * @param {number} k
 */
async function searchExactSubstring(store, query, k) {
  const pattern = `%${escapeLikePattern(query)}%`;
  const result = await store._query(
    `SELECT article_id AS id,
            chunk_index,
            headline,
            details,
            attachment_url
     FROM articles
     WHERE coalesce(headline, '') || ' ' || coalesce(details, '') ILIKE $1 ESCAPE '\\'
     ORDER BY article_id, chunk_index`,
    [pattern],
  );

  const rows = result.rows.map((row) => {
    const body = `${row.headline ?? ""} ${row.details ?? ""}`.trim();
    const { text, html } = excerptWithHighlight(body, query);
    return {
      id: row.id,
      headline: row.headline,
      attachment_url: row.attachment_url,
      chunk_index: row.chunk_index,
      details: row.details,
      text,
      html,
      score: substringScore(body, query),
    };
  });

  return groupChunkRows(rows, k);
}

export async function searchExact(query, k = 10) {
  if (!usePostgres()) return [];

  const trimmed = (query ?? "").trim();
  if (!trimmed) return [];

  let store;
  try {
    store = getPgStore();
  } catch {
    return [];
  }

  try {
    if (THAI_RE.test(trimmed)) {
      return flattenChunkResults(await searchExactSubstring(store, trimmed, k));
    }

    const ftsResults = await searchExactFts(store, trimmed, k);
    if (ftsResults.length > 0) return flattenChunkResults(ftsResults);

    return flattenChunkResults(await searchExactSubstring(store, trimmed, k));
  } catch {
    return [];
  }
}
