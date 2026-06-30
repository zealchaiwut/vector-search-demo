/**
 * OR-tsquery lexical scorer using ts_rank_cd and proximity boosting.
 *
 * English queries:
 *   - Tokenises on whitespace → joins with ' | ' → to_tsquery('english', 'term1 | term2')
 *   - Scores with ts_rank_cd so term coverage AND proximity both influence rank
 *   - Applies a proximity boost when the exact phrase appears adjacent in the document
 *   - Queries the existing `ts` column (migration 003, 'english' config)
 *
 * Thai queries:
 *   - Segments with Intl.Segmenter('th') → word tokens
 *   - Builds to_tsquery('simple', 'tok1 | tok2') from segmented tokens
 *   - Queries the `ts_simple` column (migration 008, 'simple' config)
 *   - ts_rank_cd applied; proximity boost checked with phraseto_tsquery('simple', ...)
 */

import { tokeniseQuery, segmentThai } from './thaiSegmenter.js';

const THAI_RE = /[฀-๿]/;

/**
 * Sanitise a raw term for use inside to_tsquery.
 * Removes characters that are syntactically special in tsquery expressions.
 *
 * @param {string} term
 * @returns {string}
 */
function sanitiseTerm(term) {
  return term.replace(/[&|!():*'\\<>]/g, '').trim();
}

/**
 * Build an OR tsquery string from an array of terms.
 * Returns null if no valid terms remain after sanitisation.
 *
 * @param {string[]} terms
 * @returns {string|null}
 */
function buildOrStr(terms) {
  const clean = terms.map(sanitiseTerm).filter(Boolean);
  if (clean.length === 0) return null;
  return clean.join(' | ');
}

/**
 * OR-tsquery scorer for Thai queries against the ts_simple column.
 * Falls back to pg_trgm word_similarity when ts_simple yields no results
 * (e.g. column not yet backfilled or migration not yet run).
 *
 * @param {import("../../store/PgVectorStore.js").PgVectorStore} store
 * @param {string} query
 * @param {number} k
 */
async function searchThaiOr(store, query, k) {
  const tokens = tokeniseQuery(query);
  const orStr = buildOrStr(tokens);

  if (orStr) {
    const phraseText = segmentThai(query.trim());
    const hasMultiple = tokens.length > 1;

    try {
      const result = await store._query(
        `SELECT article_id AS id,
                chunk_index,
                headline,
                details,
                attachment_url,
                ts_rank_cd(ts_simple, to_tsquery('simple', $3)) +
                  CASE WHEN $4 AND ts_simple @@ phraseto_tsquery('simple', $2)
                       THEN 0.3 ELSE 0 END AS lexical_score
         FROM articles
         WHERE ts_simple IS NOT NULL
           AND ts_simple @@ to_tsquery('simple', $3)
         ORDER BY lexical_score DESC
         LIMIT $1`,
        [k * 5, phraseText, orStr, hasMultiple],
      );

      if (result.rows.length > 0) {
        return result.rows.map((row) => ({
          id: row.id,
          chunk_index: typeof row.chunk_index === 'number' ? row.chunk_index : parseInt(row.chunk_index ?? '0', 10),
          headline: row.headline,
          details: row.details,
          attachment_url: row.attachment_url ?? null,
          lexical_score: parseFloat(row.lexical_score),
        }));
      }
    } catch {
      // ts_simple column may not exist; fall through to trigram
    }
  }

  // Fallback: pg_trgm word_similarity (works even without ts_simple)
  const { trigramScorer } = await import('./trigramScorer.js');
  return trigramScorer(store, query, k);
}

/**
 * OR-tsquery scorer for English queries against the ts column ('english' config).
 *
 * @param {import("../../store/PgVectorStore.js").PgVectorStore} store
 * @param {string} query
 * @param {number} k
 */
async function searchEnglishOr(store, query, k) {
  const terms = query.trim().split(/\s+/).filter(Boolean);
  const orStr = buildOrStr(terms);
  if (!orStr) return [];

  const hasMultiple = terms.length > 1;

  const result = await store._query(
    `SELECT article_id AS id,
            chunk_index,
            headline,
            details,
            attachment_url,
            ts_rank_cd(ts, to_tsquery('english', $3)) +
              CASE WHEN $4 AND ts @@ phraseto_tsquery('english', $2)
                   THEN 0.3 ELSE 0 END AS lexical_score
     FROM articles
     WHERE ts @@ to_tsquery('english', $3)
     ORDER BY lexical_score DESC
     LIMIT $1`,
    [k * 5, query.trim(), orStr, hasMultiple],
  );

  return result.rows.map((row) => ({
    id: row.id,
    chunk_index: typeof row.chunk_index === 'number' ? row.chunk_index : parseInt(row.chunk_index ?? '0', 10),
    headline: row.headline,
    details: row.details,
    attachment_url: row.attachment_url ?? null,
    lexical_score: parseFloat(row.lexical_score),
  }));
}

/**
 * OR-tsquery scorer — routes to Thai or English path based on script detection.
 * Conforms to the searchLexical() interface: (store, query, k) → Promise<Array>.
 *
 * @param {import("../../store/PgVectorStore.js").PgVectorStore} store
 * @param {string} query
 * @param {number} k
 */
export async function tsvectorOrScorer(store, query, k) {
  const trimmed = (query ?? '').trim();
  if (!trimmed) return [];
  return THAI_RE.test(trimmed)
    ? searchThaiOr(store, trimmed, k)
    : searchEnglishOr(store, trimmed, k);
}
