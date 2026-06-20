/**
 * Keyword (exact) search using Postgres full-text search.
 *
 * Uses plainto_tsquery + ts_rank over a generated tsvector column.
 * Only functional when DB_BACKEND=postgres; returns [] for other backends.
 *
 * Response shape per result:
 *   { id, headline, details, score, attachment_url, best_passage, passages }
 *
 * best_passage is plain text from the highest-ranked chunk snippet.
 * passages[] holds up to MAX_CHUNKS_PER_ARTICLE chunk hits with FTS highlights
 * (html field uses <strong class="kw"> on matched terms only).
 */

import { usePostgres } from "../data/backend.js";
import { getPgStore } from "../store/PgVectorStore.js";

const MAX_CHUNKS_PER_ARTICLE = 3;
const TS_HEADLINE_OPTS =
  "MaxWords=35, MinWords=15, ShortWord=3, HighlightAll=FALSE, MaxFragments=1";

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
      [trimmed, TS_HEADLINE_OPTS]
    );

    /** @type {Map<string, { id: string, headline: string, attachment_url: string|null, chunks: object[] }>} */
    const byArticle = new Map();

    for (const row of result.rows) {
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

      const html = sanitizeHeadlineHtml(row.snippet);
      entry.chunks.push({
        text: stripHtml(row.snippet),
        html,
        score: parseFloat(row.score),
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
  } catch {
    return [];
  }
}
