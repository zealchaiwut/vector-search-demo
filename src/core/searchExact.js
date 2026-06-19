/**
 * Keyword (exact) search using Postgres full-text search.
 *
 * Uses plainto_tsquery + ts_rank over a generated tsvector column.
 * Only functional when DB_BACKEND=postgres; returns [] for other backends.
 *
 * Response shape per result:
 *   { id, headline, details, score, attachment_url, best_passage }
 *
 * best_passage is a plain-text snippet from ts_headline (HTML tags stripped).
 */

import { usePostgres } from "../data/backend.js";
import { getPgStore } from "../store/PgVectorStore.js";

const TS_HEADLINE_OPTS =
  "MaxWords=35, MinWords=15, ShortWord=3, HighlightAll=FALSE, MaxFragments=1";

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
      `SELECT id, headline, details, score, attachment_url, snippet
       FROM (
         SELECT DISTINCT ON (article_id)
                article_id AS id,
                headline,
                details,
                ts_rank(ts, plainto_tsquery('english', $1)) AS score,
                attachment_url,
                ts_headline(
                  'english',
                  coalesce(headline, '') || ' ' || coalesce(details, ''),
                  plainto_tsquery('english', $1),
                  $3
                ) AS snippet
         FROM articles
         WHERE ts @@ plainto_tsquery('english', $1)
         ORDER BY article_id, ts_rank(ts, plainto_tsquery('english', $1)) DESC
       ) sub
       ORDER BY score DESC
       LIMIT $2`,
      [trimmed, k, TS_HEADLINE_OPTS]
    );

    return result.rows.map((row) => ({
      id: row.id,
      headline: row.headline,
      details: row.details,
      score: parseFloat(row.score),
      attachment_url: row.attachment_url ?? null,
      best_passage: row.snippet
        ? row.snippet.replace(/<b>/g, "").replace(/<\/b>/g, "")
        : "",
    }));
  } catch {
    return [];
  }
}
